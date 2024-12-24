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

import lzma
import asyncio_mqtt as aiomqtt

import pytak
import dronecot


class MQTTWorker(pytak.QueueWorker):
    """Queue Worker for MQTT."""

    def __init__(self, queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self.sensor_positions = {}

    async def parse_message(self, message):
        """Parse Open Drone ID message from MQTT."""
        topic = message.topic.value
        self._logger.debug("Message topic: %s", topic)
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

        self._logger.debug("Message payload: %s", payload)

        position = 0
        while position != -1:
            position = payload.find("}{")
            if position == -1:
                json_obj = json.loads(payload)
            else:
                message_payload = payload[0 : position + 1]
                payload = payload[position + 1 :]
                json_obj = json.loads(message_payload)

            if "position" in topic:
                json_obj["topic"] = topic
                await self.handle_sensor_position(json_obj)
            elif json_obj.get("data"):
                json_obj["topic"] = topic
                await self.handle_sensor_data(json_obj)
            elif json_obj.get("status"):
                json_obj["topic"] = topic
                await self.handle_sensor_status(json_obj)

    async def handle_sensor_position(self, message):
        """Process sensor position messages."""
        topic = message.get("topic")
        sensor = topic.split("/")[2]
        self.sensor_positions[sensor] = {
            "lat": message.get("lat"),
            "lon": message.get("lon"),
            "altHAE": message.get("altHAE"),
            "altMSL": message.get("altMSL"),
            "alt": message.get("alt"),
            "track": message.get("track"),
            "magtrack": message.get("magtrack"),
            "speed": message.get("speed"),
        }

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
        """Process sensor status messages."""
        status = message.get("status")
        if not status:
            return

        topic = message["topic"]
        sensor = topic.split("/")[2]

        position = self.sensor_positions.get(sensor) or {}
        pl = position | message
        self._logger.info("Publishing status for sensor: %s", sensor)
        await self.put_queue(pl)

    async def run(self, _=-1) -> None:
        """Run this Thread, Reads from Pollers."""
        self._logger.info("Running MQTTWorker")

        client_id = self.config.get("MQTT_CLIENT_ID", "dronecot")
        topic = self.config.get("MQTT_TOPIC", dronecot.DEFAULT_MQTT_TOPIC)
        broker = self.config.get("MQTT_BROKER", dronecot.DEFAULT_MQTT_BROKER)
        port = int(self.config.get("MQTT_PORT", dronecot.DEFAULT_MQTT_PORT))
        mqtt_username = self.config.get("MQTT_USERNAME")
        mqtt_password = self.config.get("MQTT_PASSWORD")

        ssl_ctx = None
        if self.config.get("MQTT_TLS_CLIENT_CERT"):
            ssl_ctx = pytak.client_functions.get_ssl_ctx(self.config)

        async with aiomqtt.Client(
            hostname=broker,
            port=port,
            username=mqtt_username or None,
            password=mqtt_password or None,
            client_id=client_id,
            tls_context=ssl_ctx,
        ) as client:
            self._logger.info("Connected to MQTT Broker %s:%d/%s", broker, port, topic)
            async with client.messages() as messages:
                await client.subscribe(topic)
                async for message in messages:
                    self._logger.debug("Received message: %s", message)
                    await self.parse_message(message)


class RIDWorker(pytak.QueueWorker):
    """Queue Worker for RID."""

    def __init__(self, queue, net_queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self.net_queue = net_queue
        self.config = config

    async def handle_data(self, data: dict) -> None:
        """Handle Data from receiver: Render to CoT, put on TX queue.

        Parameters
        ----------
        data : `list[dict, ]`
            List of craft data as key/value arrays.
        """
        self._logger.debug("Handling data: %s", data)
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
        self._logger.info("Running RIDWorker")

        while 1:
            data = await self.net_queue.get()
            if not data:
                continue

            await self.handle_data(data)
