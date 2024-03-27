#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright Sensors & Signals LLC https://www.snstac.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""DroneCOT Class Definitions."""

import base64
import json

from typing import Optional

import asyncio_mqtt as aiomqtt
from bitstruct import *
import lzma

import pytak
import dronecot

__author__ = "Greg Albrecht <gba@snstac.com>"
__copyright__ = "Copyright Sensors & Signals LLC https://www.snstac.com"
__license__ = "Apache License, Version 2.0"


class MQTTWorker(pytak.QueueWorker):
    """Queue Worker for MQTT."""

    async def parse_message(self, message):
        """Parse Open Drone ID message from MQTT."""
        try:
            # not compressed
            payload = message.payload.decode()
            # remove newline (\n) char or \0 char as it will prevent decoding of json
            if ord(payload[-1:]) == 0 or ord(payload[-1:]) == 10:
                payload = payload[:-1]
        except (UnicodeDecodeError, AttributeError):
            # lzma compressed
            payload = lzma.decompress(message.payload).decode()
            # remove \0 char as it will prevent decoding of json
            if ord(payload[-1:]) == 0:
                payload = payload[:-1]

        position = 0
        while position != -1:
            position = payload.find("}{")
            if position == -1:
                json_obj = json.loads(payload)
            else:
                message_payload = payload[0 : position + 1]
                payload = payload[position + 1 :]
                json_obj = json.loads(message_payload)

            proto = json_obj.get("protocol")
            if proto != 1.0:
                return

            if json_obj.get("data"):
                await self.handle_sensor_data(json_obj)
            elif json_obj.get("status"):
                await self.handle_sensor_status(json_obj)

    async def handle_sensor_data(self, message):
        """Process decoded data from the sensor."""
        data = message.get("data")
        uasdata = data.get("UASdata")
        if not uasdata:
            return

        uasdata = base64.b64decode(uasdata)

        valid_blocks = dronecot.decode_valid_blocks(uasdata, dronecot.ODIDValidBlocks())
        pl = dronecot.parse_payload(uasdata, valid_blocks)
        await self.put_queue(pl)

    async def handle_sensor_status(self, message):
        """Process sensor status."""
        status = message.get("status")
        if not status:
            return
        await self.put_queue(message)

    async def run(self, _=-1) -> None:
        """Run this Thread, Reads from Pollers."""
        self._logger.info("Run: MQTTWorker")

        client_id = self.config.get("MQTT_CLIENT_ID", "dronecot")
        topic = self.config.get("MQTT_TOPIC", dronecot.DEFAULT_MQTT_TOPIC)
        broker = self.config.get("MQTT_BROKER", dronecot.DEFAULT_MQTT_BROKER)
        port = self.config.get("MQTT_PORT", dronecot.DEFAULT_MQTT_PORT)
        mqtt_username = self.config.get("MQTT_USERNAME")
        mqtt_password = self.config.get("MQTT_PASSWORD")

        async with aiomqtt.Client(
            hostname=broker,
            port=port,
            username=mqtt_username,
            password=mqtt_password,
            client_id=client_id,
        ) as client:
            self._logger.info("Connected to MQTT Broker %s:%d/%s", broker, port, topic)
            async with client.messages() as messages:
                await client.subscribe(topic)
                async for message in messages:
                    await self.parse_message(message)


class RIDWorker(pytak.QueueWorker):
    """Queue Worker for RID."""

    def __init__(self, queue, net_queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self.net_queue = net_queue
        self.config = config

    async def handle_data(self, data: dict) -> None:
        """Handle Data from ADS-B receiver: Render to CoT, put on TX queue.

        Parameters
        ----------
        data : `list[dict, ]`
            List of craft data as key/value arrays.
        """
        # self._logger.info(data)
        if "status" in data:
            event = dronecot.xml_to_cot(data, self.config, "sensor_status_to_cot")
            await self.put_queue(event)
        else:
            uas_event: Optional[bytes] = dronecot.xml_to_cot(
                data, self.config, "rid_uas_to_cot_xml"
            )
            op_event: Optional[bytes] = dronecot.xml_to_cot(
                data, self.config, "rid_op_to_cot_xml"
            )
            await self.put_queue(uas_event)
            await self.put_queue(op_event)

    async def run(self, _=-1) -> None:
        """Run the main process loop."""
        self._logger.info("Run: RIDWorker")

        while 1:
            data = await self.net_queue.get()
            if not data:
                # await asyncio.sleep(0.01)
                continue

            await self.handle_data(data)
