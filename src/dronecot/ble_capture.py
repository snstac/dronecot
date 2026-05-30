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

"""BLE capture via Sniffle-compatible USB dongle (optional sniffle package)."""

import logging
import threading
from glob import glob
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

_logger = logging.getLogger(__name__)


def parse_ble_feed_url(feed_url: str) -> dict:
    """Parse ble:// FEED_URL."""
    parsed = urlparse(feed_url)
    path = (parsed.path or "").strip()
    if path.startswith("//"):
        path = path[2:]

    serial = path or parsed.hostname
    if serial == "auto":
        serial = None

    qs = parse_qs(parsed.query or "")
    baud = int(qs.get("baud", [2000000])[0])
    long_range = qs.get("long_range", ["1"])[0].lower() in {"1", "true", "yes"}
    extended = qs.get("extended", ["1"])[0].lower() in {"1", "true", "yes"}

    return {
        "serial": serial,
        "baud": baud,
        "long_range": long_range,
        "extended": extended,
    }


def find_sniffle_port() -> Optional[str]:
    """Auto-detect Sniffle dongle serial port."""
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        return None

    for port in comports():
        if port.vid == 0x10C4 and port.pid == 0xEA60:
            if port.manufacturer in ("ITead", "Silicon Labs"):
                return port.device
        if port.vid == 0x0451 and port.pid == 0xBEF3:
            return port.device

    candidates = sorted(glob("/dev/serial/by-id/*Sniffle*"))
    if candidates:
        return candidates[0]
    candidates = sorted(glob("/dev/ttyACM*")) + sorted(glob("/dev/ttyUSB*"))
    return candidates[0] if candidates else None


class BleSniffer:
    """
    Sniffle BLE sniffer wrapper.

    Requires the Sniffle python_cli package on PYTHONPATH (GPLv3, user-installed):
    https://github.com/nccgroup/Sniffle
    """

    def __init__(
        self,
        on_packet: Callable,
        serial_port: Optional[str] = None,
        baud: int = 2000000,
        long_range: bool = True,
        extended: bool = True,
    ):
        self.on_packet = on_packet
        self.serial_port = serial_port or find_sniffle_port()
        self.baud = baud
        self.long_range = long_range
        self.extended = extended
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hw = None

    def _run(self) -> None:
        try:
            from sniffle.sniffle_hw import make_sniffle_hw  # pylint: disable=import-outside-toplevel
            from sniffle.constants import PhyMode  # pylint: disable=import-outside-toplevel
            from sniffle.packet_decoder import PacketMessage  # pylint: disable=import-outside-toplevel
            from dronecot import ble_parse
        except ImportError as exc:
            _logger.error(
                "BLE capture requires Sniffle. Clone https://github.com/nccgroup/Sniffle "
                "and add python_cli to PYTHONPATH, or: pip install -e /path/to/Sniffle/python_cli"
            )
            raise ImportError(
                "Sniffle python package not found. See docs/feeds.md for setup."
            ) from exc

        if not self.serial_port:
            raise IOError("No Sniffle serial port found (set BLE_SERIAL)")

        self._hw = make_sniffle_hw(self.serial_port, baudrate=self.baud)

        if self.long_range:
            self._hw.cmd_chan_aa_phy(37, phy=PhyMode.PHY_CODED_S8)
            if self.extended:
                self._hw.cmd_ext_adv_hop(enable=True)
        else:
            self._hw.cmd_chan_aa_phy(37, phy=PhyMode.PHY_1M)

        self._hw.cmd_follow(False)
        self._hw.cmd_rssi()

        while not self._stop.is_set():
            try:
                msg = self._hw.recv_and_decode()
            except Exception as exc:  # pylint: disable=broad-except
                if self._stop.is_set():
                    break
                _logger.debug("Sniffle recv error: %s", exc)
                continue

            if not isinstance(msg, PacketMessage):
                continue

            adv_data = getattr(msg, "adv_data", None) or getattr(msg, "body", None)
            if not adv_data:
                continue

            mac = getattr(msg, "a", None) or getattr(msg, "adv_addr", None)
            rssi = getattr(msg, "rssi", None)
            if mac is not None and not isinstance(mac, bytes):
                try:
                    mac = bytes(mac)
                except (TypeError, ValueError):
                    mac = None

            result = ble_parse.extract_odid_from_sniffle_adv(
                bytes(adv_data), mac=mac, rssi=rssi
            )
            if result:
                pack, meta = result
                self.on_packet(pack, meta)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dronecot-ble-sniff"
        )
        self._thread.start()
        _logger.info("BLE sniffer starting on %s", self.serial_port)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._hw and hasattr(self._hw, "ser"):
            try:
                self._hw.ser.close()
            except Exception:  # pylint: disable=broad-except
                pass
