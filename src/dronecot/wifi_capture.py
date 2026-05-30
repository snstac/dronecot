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

"""Wi-Fi monitor-mode capture helpers (iw + Scapy)."""

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

_logger = logging.getLogger(__name__)


def parse_wifi_feed_url(feed_url: str) -> dict:
    """Parse wifi://, wireless://, or wifi+pcap:// FEED_URL."""
    parsed = urlparse(feed_url)
    if parsed.scheme == "wireless":
        feed_url = feed_url.replace("wireless://", "wifi://", 1)
        parsed = urlparse(feed_url)
    path = (parsed.path or "").strip()
    if path.startswith("//"):
        path = path[2:]

    interface = path or parsed.hostname
    qs = parse_qs(parsed.query or "")
    hop_channels = None
    hop_dwell = None
    if "hop" in qs:
        hop_channels = [int(x.strip()) for x in qs["hop"][0].split(",") if x.strip()]
    if "dwell" in qs:
        parts = qs["dwell"][0].split(",")
        hop_dwell = tuple(float(x.strip()) for x in parts if x.strip())

    channel = int(qs.get("channel", [parsed.port or 6])[0])

    pcap_path = None
    if "pcap" in parsed.scheme or parsed.scheme.startswith("wifi+pcap"):
        pcap_path = path or parsed.netloc

    return {
        "interface": interface,
        "channel": channel,
        "hop_channels": hop_channels,
        "hop_dwell": hop_dwell or (3.0, 1.0),
        "pcap_path": pcap_path,
    }


def run_iw(args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run iw with common defaults."""
    cmd = ["iw", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def set_monitor_mode(interface: str) -> bool:
    """Put interface into monitor mode."""
    try:
        run_iw(["dev", interface, "set", "type", "monitor"], check=False)
        subprocess.run(
            ["ip", "link", "set", interface, "up"],
            capture_output=True,
            check=False,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        _logger.error("Failed to set monitor mode on %s: %s", interface, exc)
        return False


def set_managed_mode(interface: str) -> None:
    """Restore managed mode."""
    try:
        run_iw(["dev", interface, "set", "type", "managed"], check=False)
        subprocess.run(
            ["ip", "link", "set", interface, "up"],
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def set_channel(interface: str, channel: int) -> None:
    """Set Wi-Fi channel via iw."""
    try:
        run_iw(["dev", interface, "set", "channel", str(channel)], check=False)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        _logger.debug("set channel failed: %s", exc)


def channel_hopper(
    interface: str,
    channels: Tuple[int, ...],
    dwell_times: Tuple[float, ...],
    stop_event: threading.Event,
) -> None:
    """Hop between channels until stop_event is set."""
    idx = 0
    while not stop_event.is_set():
        channel = channels[idx % len(channels)]
        dwell = dwell_times[idx % len(dwell_times)]
        set_channel(interface, channel)
        end = time.time() + dwell
        while time.time() < end and not stop_event.is_set():
            time.sleep(0.1)
        idx += 1


class WifiSniffer:
    """Scapy-based Wi-Fi sniffer running in a background thread."""

    def __init__(
        self,
        on_packet: Callable,
        interface: Optional[str] = None,
        pcap_path: Optional[str] = None,
        channel: int = 6,
        hop_channels: Optional[List[int]] = None,
        hop_dwell: Tuple[float, float] = (3.0, 1.0),
    ):
        self.on_packet = on_packet
        self.interface = interface
        self.pcap_path = pcap_path
        self.channel = channel
        self.hop_channels = hop_channels
        self.hop_dwell = hop_dwell
        self._stop = threading.Event()
        self._hop_stop = threading.Event()
        self._hop_thread: Optional[threading.Thread] = None
        self._sniffer = None
        self._monitor_enabled = False

    def _packet_handler(self, packet) -> None:
        try:
            from dronecot import wifi_parse

            result = wifi_parse.extract_odid_from_scapy_packet(packet)
            if result:
                pack, meta = result
                if self.interface and "channel" not in meta:
                    meta["channel"] = self.channel
                self.on_packet(pack, meta)
        except Exception as exc:  # pylint: disable=broad-except
            _logger.debug("packet handler error: %s", exc)

    def start(self) -> None:
        try:
            from scapy.all import AsyncSniffer  # pylint: disable=import-outside-toplevel
            from scapy.layers.dot11 import Dot11  # noqa: F401 pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise ImportError(
                "Wi-Fi capture requires scapy. Install with: pip install 'dronecot[wifi]'"
            ) from exc

        if self.pcap_path:
            path = Path(self.pcap_path)
            if not path.exists():
                raise FileNotFoundError(f"pcap not found: {path}")
            self._sniffer = AsyncSniffer(
                offline=str(path),
                lfilter=lambda p: p.haslayer("Dot11"),
                prn=self._packet_handler,
                store=False,
            )
            self._sniffer.start()
            return

        if not self.interface:
            raise ValueError("Wi-Fi interface required for live capture")

        self._monitor_enabled = set_monitor_mode(self.interface)
        set_channel(self.interface, self.channel)

        if self.hop_channels and len(self.hop_channels) >= 2:
            self._hop_stop.clear()
            self._hop_thread = threading.Thread(
                target=channel_hopper,
                args=(
                    self.interface,
                    tuple(self.hop_channels),
                    self.hop_dwell,
                    self._hop_stop,
                ),
                daemon=True,
                name="dronecot-wifi-hop",
            )
            self._hop_thread.start()

        self._sniffer = AsyncSniffer(
            iface=self.interface,
            lfilter=lambda p: p.haslayer("Dot11")
            and p.getlayer("Dot11").subtype in {8, 13},
            prn=self._packet_handler,
            store=False,
        )
        self._sniffer.start()
        _logger.info(
            "Wi-Fi sniffer started on %s channel %s", self.interface, self.channel
        )

    def stop(self) -> None:
        self._hop_stop.set()
        if self._hop_thread:
            self._hop_thread.join(timeout=2)
        if self._sniffer:
            try:
                self._sniffer.stop()
            except Exception:  # pylint: disable=broad-except
                pass
            self._sniffer = None
        if self._monitor_enabled and self.interface:
            set_managed_mode(self.interface)
