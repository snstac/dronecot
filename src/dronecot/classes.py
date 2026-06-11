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
import time
import asyncio
import os
import ssl
from pathlib import Path

from socket import socket
from typing import Optional, Union
from urllib.parse import urlparse

import lzma

try:
    import aiomqtt
except ImportError:
    aiomqtt = None  # type: ignore[assignment]

import pytak
import dronecot


class SerialWorker(pytak.QueueWorker):
    """Queue Worker for MAVLink serial Open Drone ID."""

    def __init__(self, queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self.config = config

    def _parse_serial_config(self):
        """Parse serial connection settings from FEED_URL or explicit config values."""
        feed_url = str(self.config.get("FEED_URL", dronecot.DEFAULT_FEED_URL))
        parsed = urlparse(feed_url)

        serial_port = self.config.get("SERIAL_PORT")
        baud_rate_raw = self.config.get("SERIAL_BAUD_RATE")

        if not serial_port or not baud_rate_raw:
            # Supports:
            # - serial:///dev/ttyACM1:115200
            # - serial:///dev/ttyACM1
            # - serial://localhost:115200 (hostname form)
            path_part = (parsed.path or "").strip()
            if path_part.startswith("//"):
                path_part = path_part[1:]

            path_port = path_part
            path_baud = None
            if ":" in path_part:
                path_port, path_baud = path_part.rsplit(":", maxsplit=1)

            serial_port = serial_port or path_port or parsed.hostname
            baud_rate_raw = baud_rate_raw or path_baud or parsed.port

        baud_rate = int(baud_rate_raw or dronecot.DEFAULT_SERIAL_BAUD_RATE)

        if not serial_port:
            serial_port = dronecot.DEFAULT_SERIAL_PORT

        return serial_port, baud_rate

    def _mavlink_pack_to_parse_payload_schema(self, messages, pack_size) -> dict:
        """Convert MAVLink OPEN_DRONE_ID_MESSAGE_PACK to parse_payload-like schema."""
        parsed = dronecot.odid.message_pack_to_dict(messages, pack_size)
        return dronecot.rid_normalize.odid_parsed_to_rid_dict(parsed)

    async def run(self, _=-1) -> None:
        """Read MAVLink messages from serial and enqueue decoded ODID payloads."""
        self._logger.info("Running SerialWorker")

        try:
            from pymavlink import mavutil
            from serial.serialutil import SerialException
        except ImportError as exc:
            self._logger.error("Missing SerialWorker dependency: %s", exc)
            return

        while True:
            interface, baudrate = self._parse_serial_config()
            self._logger.info(
                "Opening MAVLink serial interface=%s baudrate=%s", interface, baudrate
            )

            try:
                master = await asyncio.to_thread(
                    mavutil.mavlink_connection, interface, baudrate
                )
                await asyncio.to_thread(master.wait_heartbeat, timeout=20)
                self._logger.info("MAVLink heartbeat received")
            except SerialException as exc:
                self._logger.error(
                    "Serial read failed while waiting for MAVLink heartbeat "
                    "(port=%s baud=%s): %s",
                    interface,
                    baudrate,
                    exc,
                )
                await asyncio.sleep(2)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                self._logger.error(
                    "MAVLink setup/heartbeat failed for %s:%s: %s",
                    interface,
                    baudrate,
                    exc,
                )
                await asyncio.sleep(2)
                continue

            while True:
                try:
                    msg = await asyncio.to_thread(master.recv_match)
                except SerialException as exc:
                    self._logger.error(
                        "Serial read failed while receiving MAVLink data: %s", exc
                    )
                    await asyncio.sleep(1)
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    self._logger.debug("Unhandled MAVLink receive exception: %s", exc)
                    await asyncio.sleep(0.1)
                    continue

                if not msg:
                    await asyncio.sleep(0.1)
                    continue

                msg_type = msg.get_type()
                if msg_type == "OPEN_DRONE_ID_MESSAGE_PACK":
                    parsed_payload = self._mavlink_pack_to_parse_payload_schema(
                        msg.messages, msg.msg_pack_size
                    )
                    await self.put_queue(parsed_payload)
                elif msg_type == "HEARTBEAT":
                    self._logger.debug(
                        "MAVLink heartbeat received at %s",
                        time.strftime("%H:%M:%S", time.localtime()),
                    )
                else:
                    self._logger.debug("Ignoring MAVLink message type: %s", msg_type)


class MQTTWorker(pytak.QueueWorker):
    """Queue Worker for MQTT."""

    def __init__(self, queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self.sensor_positions = {}

    async def handle_data(self, data) -> None:
        """Handle Open Drone ID message from MQTT."""
        self._logger.debug("Handling data: %s", data)
        if aiomqtt and isinstance(data, aiomqtt.Message):
            await self.parse_message(data)
        else:
            self._logger.error("Received unexpected data type: %s", type(data))

    async def parse_message(self, message):
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
        meta = dict(data)
        meta.update(dronecot.rid_normalize.uas_meta_defaults(self.config))
        pl = dronecot.rid_normalize.cuas_blob_to_rid_dict(uasdata, meta)
        if not pl:
            self._logger.error("Failed to decode UASdata payload")
            return
        pl["topic"] = message["topic"]
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

    def _resolve_path(self, value):
        """Resolve a configured file path using common runtime bases."""
        if not value:
            return None

        expanded = Path(os.path.expanduser(str(value)))
        if expanded.is_absolute():
            return str(expanded)

        candidates = [
            Path.cwd() / expanded,
            Path.home() / expanded,
            Path.home() / "work/SNS/dronecot" / expanded,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        # Fall back to cwd-relative for clearer error messages.
        return str(candidates[0])

    async def run(self, _=-1) -> None:
        """Run this Thread, Reads from Pollers."""
        if not aiomqtt:
            raise ImportError(
                "aiomqtt is required for MQTT support: pip install aiomqtt"
            )
        self._logger.info("Running MQTTWorker")

        # This must be unique per client, so use the sensor ID
        client_id = self.config.get("MQTT_CLIENT_ID", dronecot.DEFAULT_SENSOR_ID)

        feed_url = urlparse(self.config.get("FEED_URL", dronecot.DEFAULT_FEED_URL))
        broker = feed_url.hostname or feed_url.netloc
        port = int(feed_url.port or (8883 if feed_url.scheme in {"mqtts", "ssl"} else 1883))

        topic = self.config.get("MQTT_TOPIC", dronecot.DEFAULT_MQTT_TOPIC)
        mqtt_username = self.config.get("MQTT_USERNAME")
        mqtt_password = self.config.get("MQTT_PASSWORD")

        ssl_ctx = None
        mqtt_tls_client_cert = self.config.get("MQTT_TLS_CLIENT_CERT")
        mqtt_tls_client_key = self.config.get("MQTT_TLS_CLIENT_KEY")
        mqtt_tls_ca_file = self.config.get("MQTT_TLS_CLIENT_CAFILE")
        mqtt_tls_ciphers = self.config.get("MQTT_TLS_CLIENT_CIPHERS")
        mqtt_tls_dont_verify = self.config.get("MQTT_TLS_DONT_VERIFY")
        mqtt_tls_dont_check_hostname = self.config.get("MQTT_TLS_DONT_CHECK_HOSTNAME")

        # MQTT TLS is independent from TAK TLS. Do not call PyTAK get_ssl_ctx() here.
        if (
            mqtt_tls_client_cert
            or mqtt_tls_client_key
            or mqtt_tls_ca_file
            or port == 8883
            or feed_url.scheme in {"mqtts", "ssl"}
        ):
            ssl_ctx = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH,
                cafile=mqtt_tls_ca_file or None,
            )
            if mqtt_tls_ciphers:
                ssl_ctx.set_ciphers(mqtt_tls_ciphers)

            dont_verify = str(mqtt_tls_dont_verify or "").lower() in {"1", "true", "yes", "on"}
            dont_check_hostname = str(mqtt_tls_dont_check_hostname or "").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if dont_verify:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            elif dont_check_hostname:
                ssl_ctx.check_hostname = False

            if mqtt_tls_client_cert:
                cert_path = self._resolve_path(mqtt_tls_client_cert)
                key_path = self._resolve_path(mqtt_tls_client_key) if mqtt_tls_client_key else None
                if os.path.exists(cert_path) and (not key_path or os.path.exists(key_path)):
                    ssl_ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                else:
                    self._logger.warning(
                        "MQTT TLS client cert/key not found; continuing without client cert "
                        "(cert=%s key=%s)",
                        cert_path,
                        key_path,
                    )

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
                self._logger.info("Subscribed to topic: %s", topic)
                async for message in messages:
                    self._logger.debug("Received MQTT message: %s", message)
                    await self.handle_data(message)


class WifiWorker(pytak.QueueWorker):
    """Queue Worker for Wi-Fi monitor-mode Open Drone ID capture."""

    def __init__(self, queue, config):
        super().__init__(queue, config)
        self.config = config
        self._loop = None
        self._sniffer = None

    def _on_wifi_packet(self, pack: bytes, meta: dict) -> None:
        merged = {**dronecot.rid_normalize.uas_meta_defaults(self.config), **meta}
        pl = dronecot.rid_normalize.bytes_to_rid_dict(pack, merged)
        if pl and self._loop:
            asyncio.run_coroutine_threadsafe(self.put_queue(pl), self._loop)

    async def run(self, _=-1) -> None:
        self._logger.info("Running WifiWorker")
        self._loop = asyncio.get_running_loop()

        try:
            from dronecot.wifi_capture import WifiSniffer, parse_wifi_feed_url
        except ImportError as exc:
            self._logger.error("Wi-Fi capture unavailable: %s", exc)
            return

        feed_url = str(self.config.get("FEED_URL", dronecot.DEFAULT_FEED_URL))
        feed = parse_wifi_feed_url(feed_url)

        interface = self.config.get("WIFI_INTERFACE") or feed.get("interface")
        pcap_path = self.config.get("WIFI_PCAP") or feed.get("pcap_path")
        channel = int(self.config.get("WIFI_CHANNEL", feed.get("channel", 6)))

        hop_channels = feed.get("hop_channels")
        hop_raw = self.config.get("WIFI_HOP_CHANNELS")
        if hop_raw:
            hop_channels = [int(x.strip()) for x in str(hop_raw).split(",") if x.strip()]

        dwell_raw = self.config.get("WIFI_HOP_DWELL", "3,1")
        dwell_parts = tuple(float(x.strip()) for x in str(dwell_raw).split(",") if x.strip())
        if len(dwell_parts) < 2:
            dwell_parts = feed.get("hop_dwell", (3.0, 1.0))

        self._sniffer = WifiSniffer(
            on_packet=self._on_wifi_packet,
            interface=interface,
            pcap_path=pcap_path,
            channel=channel,
            hop_channels=hop_channels,
            hop_dwell=dwell_parts,
        )

        try:
            self._sniffer.start()
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.error("Wi-Fi capture failed: %s", exc)
        finally:
            if self._sniffer:
                self._sniffer.stop()


class BleWorker(pytak.QueueWorker):
    """Queue Worker for BLE Open Drone ID capture (Sniffle dongle)."""

    def __init__(self, queue, config):
        super().__init__(queue, config)
        self.config = config
        self._loop = None
        self._sniffer = None

    def _on_ble_packet(self, pack: bytes, meta: dict) -> None:
        merged = {**dronecot.rid_normalize.uas_meta_defaults(self.config), **meta}
        pl = dronecot.rid_normalize.bytes_to_rid_dict(pack, merged)
        if pl and self._loop:
            asyncio.run_coroutine_threadsafe(self.put_queue(pl), self._loop)

    async def run(self, _=-1) -> None:
        self._logger.info("Running BleWorker")
        self._loop = asyncio.get_running_loop()

        try:
            from dronecot.ble_capture import BleSniffer, parse_ble_feed_url
        except ImportError as exc:
            self._logger.error("BLE capture unavailable: %s", exc)
            return

        feed_url = str(self.config.get("FEED_URL", ""))
        feed = parse_ble_feed_url(feed_url)

        serial = self.config.get("BLE_SERIAL") or feed.get("serial")
        baud = int(self.config.get("BLE_BAUD_RATE", feed.get("baud", 2000000)))
        long_range = str(self.config.get("BLE_LONG_RANGE", "1")).lower() in {
            "1",
            "true",
            "yes",
        }
        extended = str(self.config.get("BLE_EXTENDED", "1")).lower() in {
            "1",
            "true",
            "yes",
        }

        self._sniffer = BleSniffer(
            on_packet=self._on_ble_packet,
            serial_port=serial,
            baud=baud,
            long_range=long_range,
            extended=extended,
        )

        try:
            self._sniffer.start()
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.error("BLE capture failed: %s", exc)
        finally:
            if self._sniffer:
                self._sniffer.stop()


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
            self._logger.info("Processing sensor status data")
            event = dronecot.cot_to_xml(data, self.config, "sensor_status_to_cot")
            if event:
                await self.put_queue(event)
        else:
            self._logger.info("Processing RID data")
            cot_funcs = ["rid_uas_to_cot_xml", "rid_op_to_cot_xml"]
            for func in cot_funcs:
                event = dronecot.cot_to_xml(data, self.config, func)
                if event:
                    await self.put_queue(event)

    async def run(self, _=-1) -> None:
        """Run the main process loop."""
        self._logger.info("Running RIDWorker")

        while True:
            data = await self.net_queue.get()
            if not data:
                continue

            await self.handle_data(data)


class RXMockWorker(pytak.RXWorker):
    """Queue Worker for RX Mock Data."""

    def __init__(self, queue, config):
        """Initialize this class."""
        super().__init__(queue, config)
        self._logger.info("Initialized RXMockWorker")
        self.config = config

    async def handle_data(self, data: dict) -> None:
        """Handle Data from receiver: Render to CoT, put on TX queue.

        Parameters
        ----------
        data : `list[dict, ]`
            List of craft data as key/value arrays.
        """
        self._logger.info("Handling data: %s", data)
        del data


# ---------------------------------------------------------------------------
# DJI Drone ID worker classes (AntSDR binary + text CSV protocols)
# ---------------------------------------------------------------------------

class DJIWorker(pytak.QueueWorker):
    """Process DJI Drone ID data from a net queue and emit CoT events."""

    def __init__(self, tx_queue: asyncio.Queue, config, net_queue: asyncio.Queue) -> None:
        super().__init__(tx_queue, config)
        self.net_queue = net_queue

    async def handle_data(self, data) -> None:
        if isinstance(data, str):
            events = dronecot.dji_handle_text_line(data, self.config)
        elif isinstance(data, bytes) and data.startswith(b"dji_O,"):
            events = dronecot.dji_handle_text_line(data.decode("utf-8", errors="replace"), self.config)
        else:
            events = dronecot.dji_handle_frame(data, self.config)
        for event in events:
            await self.put_queue(event)

    async def run(self, _=-1) -> None:
        self._logger.info("Running %s", self.__class__)
        while True:
            received = await self.net_queue.get()
            if not received:
                continue
            await self.handle_data(received)


class _DJIFeedWorker(pytak.QueueWorker):
    """Base class for DJI feed workers that enqueue raw data."""

    async def handle_data(self, data) -> None:
        self.queue.put_nowait(data)


class DJINetWorker(_DJIFeedWorker):
    """Read binary DJI Drone ID frames from a TCP connection (port 41030)."""

    async def run(self, _=-1) -> None:
        url = urlparse(self.config.get("FEED_URL", dronecot.DEFAULT_DJI_FEED_URL))
        self._logger.info("Running %s for %s", self.__class__, url.geturl())
        host, port = url.netloc.split(":")
        reader, _ = await asyncio.open_connection(host, int(port))
        read_bytes = int(self.config.get("READ_BYTES", dronecot.DEFAULT_DJI_READ_BYTES))
        while True:
            try:
                received = await reader.read(read_bytes)
                if received:
                    await self.handle_data(received)
                    await asyncio.sleep(0.001)
                else:
                    await asyncio.sleep(0.1)
            except Exception as exc:
                self._logger.error("DJI read error: %s", exc)
                await asyncio.sleep(1)


class DJITextWorker(_DJIFeedWorker):
    """Read AntSDR text CSV lines from a TCP connection (port 52002)."""

    async def run(self, _=-1) -> None:
        url = urlparse(self.config.get("FEED_URL", dronecot.DEFAULT_DJI_TEXT_FEED_URL))
        self._logger.info("Running %s for %s", self.__class__, url.geturl())
        host, port = url.netloc.split(":")
        reader, _ = await asyncio.open_connection(host, int(port))
        buffer = b""
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                continue
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", maxsplit=1)
                text = line.decode("utf-8", errors="replace").strip()
                if text.startswith("dji_O,"):
                    await self.handle_data(text)


class DJIFileWorker(_DJIFeedWorker):
    """Replay AntSDR text log lines from a local file for offline testing."""

    async def run(self, _=-1) -> None:
        url = urlparse(self.config.get("FEED_URL", dronecot.DEFAULT_DJI_FEED_URL))
        path = Path(url.path)
        self._logger.info("Running %s for %s", self.__class__, path)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                text = line.strip()
                if text.startswith("dji_O,"):
                    await self.handle_data(text)
                await asyncio.sleep(0)


class DJIListenerWorker(pytak.QueueWorker):
    """Accept incoming TCP connections from DJI RF scanners (server mode)."""

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self._logger.info("DJI client connected from %s", peer)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=5.0)
                    data = data.rstrip(b"\n")
                except asyncio.TimeoutError:
                    data = await reader.read(1024)
                except asyncio.IncompleteReadError as exc:
                    data = exc.partial
                    if not data:
                        break
                    break
                if b"=" in data:
                    continue
                if not data:
                    break
                self.queue.put_nowait(data)
                await asyncio.sleep(0.001)
        except Exception as exc:
            self._logger.error("DJI client error %s: %s", peer, exc)
        finally:
            writer.close()
            await writer.wait_closed()

    async def run(self, _=-1) -> None:
        bind = self.config.get("DJI_BIND_ADDRESS", dronecot.DEFAULT_DJI_BIND_ADDRESS)
        port = self.config.get("DJI_TCP_PORT", dronecot.DEFAULT_DJI_TCP_PORT)
        self._logger.info("Running %s on %s:%s", self.__class__, bind, port)
        server = await asyncio.start_server(self._handle_client, bind, port)
        async with server:
            await server.serve_forever()


# Backward-compatible aliases matching djicot names
NetWorker = DJINetWorker
BinaryNetWorker = DJINetWorker
TextNetWorker = DJITextWorker
FileReplayWorker = DJIFileWorker
TCPListenerWorker = DJIListenerWorker


# ---------------------------------------------------------------------------
# UDP pre-decoded Remote ID receiver
# ---------------------------------------------------------------------------

class UDPRIDWorker(pytak.QueueWorker):
    """Receive pre-decoded Remote ID JSON datagrams over UDP (default port 9999).

    Listens for flat JSONL datagrams from drone detection nodes that decode
    ASTM F3411 Remote ID payloads locally and broadcast them on the LAN.
    Each datagram is normalised into a RIDWorker-compatible dict.
    """

    def __init__(self, queue: asyncio.Queue, config) -> None:
        super().__init__(queue, config)
        self.config = config

    async def run(self, _=-1) -> None:
        from .udp_rid import parse_udp_rid_line

        bind_host = str(self.config.get("UDP_RID_HOST", dronecot.DEFAULT_UDP_RID_HOST))
        bind_port = int(self.config.get("UDP_RID_PORT", dronecot.DEFAULT_UDP_RID_PORT))

        loop = asyncio.get_running_loop()
        worker = self

        class _Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:
                    return
                pl = parse_udp_rid_line(text, worker.config)
                if pl:
                    asyncio.run_coroutine_threadsafe(worker.put_queue(pl), loop)

            def error_received(self, exc):
                worker._logger.warning("UDPRIDWorker error: %s", exc)

        transport, _ = await loop.create_datagram_endpoint(
            _Proto,
            local_addr=(bind_host, bind_port),
            allow_broadcast=True,
        )
        self._logger.info(
            "UDPRIDWorker listening on UDP %s:%s",
            bind_host, bind_port,
        )
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        finally:
            transport.close()
