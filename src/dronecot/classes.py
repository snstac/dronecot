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

from socket import socket
from typing import Optional, Union

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

    async def handle_data(self, data: Union[dict, aiomqtt.Message]) -> None:
        """Handle Open Drone ID message from MQTT.

        Parameters
        ----------
        data : `list[dict, aiomqtt.Message]`
            List of craft data as key/value arrays.
        """
        self._logger.debug("Handling data: %s", data)
        if isinstance(data, aiomqtt.Message):
            await self.parse_message(data)
        else:
            self._logger.error("Received unexpected data type: %s", type(data))

    async def parse_message(self, message: aiomqtt.Message):
        """Parse Open Drone ID message from MQTT."""
        self._logger.debug("Parsing message: %s", message)

        topic = message.topic.value
        self._logger.debug("Message topic: %s", topic)

        _payload = message.payload
        if not isinstance(_payload, bytes):
            self._logger.error("Message contained no bytes payload.")
            return

        payload = await self.decode_payload(_payload)
        if not payload:
            self._logger.error("Failed to decode message payload")
            return

        await self.process_payload(payload, topic)

    async def decode_payload(self, payload: bytes) -> Optional[str]:
        """Decode the MQTT message payload, which could be either plain JSON or LZMA compressed JSON."""
        _payload = None

        try:
            # Not compressed
            _payload = payload.decode()
            # Remove newline (\n) char or \0 char as it will prevent decoding of JSON
            if ord(payload[-1:]) in {0, 10}:
                _payload = _payload[:-1]
        except (UnicodeDecodeError, AttributeError):
            # LZMA compressed
            try:
                _payload = lzma.decompress(payload).decode()
            except lzma.LZMAError as e:
                self._logger.error("LZMA decompression error: %s", e)
                return None
            # Remove \0 char as it will prevent decoding of JSON
            if ord(_payload[-1:]) == 0:
                _payload = _payload[:-1]

        return _payload

    async def process_payload(self, payload: str, topic: str) -> None:
        """Process the payload into individual JSON objects and handle them."""
        self._logger.debug("Processing payload (%s): %s", topic, payload)
        json_end_position = 0
        while json_end_position != -1:
            message_payload = payload

            # Look for the next JSON object in the payload, which is (sometimes)
            # separated by "}{". If found, split the payload at that position.
            json_end_position = payload.find("}{")
            if json_end_position != -1:
                message_payload = payload[0 : json_end_position + 1]
                # Start payload over at the next JSON object
                payload = payload[json_end_position + 1 :]

            json_obj = json.loads(message_payload)
            json_obj["topic"] = topic

            if "position" in topic:
                await self.handle_sensor_position(json_obj)
            elif json_obj.get("data"):
                await self.handle_sensor_data(json_obj)
            elif json_obj.get("status"):
                await self.handle_sensor_status(json_obj)

    async def handle_sensor_position(self, message):
        """Process sensor position messages."""
        self._logger.debug("Handling sensor position message: %s", message)
        topic = message.get("topic")
        sensor = topic.split("/")[2]
        self.sensor_positions[sensor] = {
            "sensor_id": sensor,
            "lat": message.get("lat"),
            "lon": message.get("lon"),
            "altHAE": message.get("altHAE"),
            "altMSL": message.get("altMSL"),
            "alt": message.get("alt"),
            "track": message.get("track"),
            "magtrack": message.get("magtrack"),
            "speed": message.get("speed"),
        }

    async def handle_sensor_data(self, message: dict):
        """Process decoded data from the sensor."""
        self._logger.debug("Handling sensor data message: %s", message)

        protocol = message.get("protocol")
        if not protocol or str(protocol) != "1.0":
            self._logger.error("Unsupported protocol: %s", protocol)
            return

        data = message.get("data", {})
        if not data:
            self._logger.error("No data in message")
            return

        uasdata = data.get("UASdata")
        if not uasdata:
            self._logger.error("No UASdata in message")
            return

        uasdata = base64.b64decode(uasdata)

        valid_blocks = dronecot.decode_valid_blocks(uasdata, dronecot.ODIDValidBlocks())
        pl = dronecot.parse_payload(uasdata, valid_blocks)
        del data["UASdata"]
        pl["data"] = data
        pl["topic"] = message["topic"]
        pl["extra"] = message.get("extra", {})
        await self.put_queue(pl)

    async def handle_sensor_status(self, message: dict):
        """Process sensor status messages."""
        self._logger.debug("Handling sensor status message: %s", message)

        status = message.get("status")
        if not status:
            self._logger.error("No status in message")
            return

        topic = message["topic"]
        sensor = topic.split("/")[2]

        position = self.sensor_positions.get(sensor) or {}
        pl = position | message
        del pl["topic"]
        pl["sensor_id"] = sensor
        self._logger.info("Publishing status for sensor: %s", sensor)
        self._logger.debug("Status: %s", pl)
        await self.put_queue(pl)

    async def run(self, _=-1) -> None:
        """Run this Thread, Reads from Pollers."""
        self._logger.info("Running MQTTWorker")

        # This must be unique per client, so use the sensor ID
        client_id = self.config.get("MQTT_CLIENT_ID", dronecot.DEFAULT_SENSOR_ID)

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
                    self._logger.debug("Received MQTT message: %s", message)
                    await self.handle_data(message)


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

        if "status" in data and "position" not in data.get("topic", ""):
            event = dronecot.xml_to_cot(data, self.config, "sensor_status_to_cot")
            await self.put_queue(event)
        else:
            cot_funcs = ["rid_uas_to_cot_xml", "rid_op_to_cot_xml"]
            for func in cot_funcs:
                event = dronecot.cot_to_xml(data, self.config, func)
                print(event)
                await self.put_queue(event)

    async def run(self, _=-1) -> None:
        """Run the main process loop."""
        self._logger.info("Running RIDWorker")

        while True:
            data = await self.net_queue.get()
            if not data:
                continue

            await self.handle_data(data)
