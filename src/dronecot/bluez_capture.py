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

"""Bluetooth Remote ID capture on a stock BlueZ adapter -- no Sniffle dongle.

``ble_capture`` needs a Sniffle nRF52 dongle, which means a box with no extra
hardware decodes no Bluetooth Remote ID at all. Every Raspberry Pi already has a
Bluetooth radio that can hear ASTM F3411 advertisements, so this module reads
them through BlueZ instead.

Two cooperating pieces
----------------------
**Scan driver** (always): BlueZ D-Bus ``SetDiscoveryFilter`` + ``StartDiscovery``
puts the controller into a continuous LE scan. This is a normal D-Bus client, so
it coexists with ``bluetoothd`` and with an active Bluetooth PAN rather than
seizing the adapter.

**Reader** (selectable):

``monitor``
    An ``HCI_CHANNEL_MONITOR`` socket -- the same passive tap ``btmon`` uses.
    Delivers every LE Advertising Report the controller receives, with the full
    advertisement bytes and per-frame RSSI, and nothing is coalesced. Needs
    ``CAP_NET_RAW``. It is purely passive, so it only sees traffic while the
    scan driver (or anything else) is scanning.

``dbus``
    Reads the ``ServiceData`` property off ``org.bluez.Device1``. Requires no
    elevated capability, but BlueZ may coalesce repeated advertisements from one
    device, which for Remote ID means dropped messages -- a transmitter rotates
    through message types, so a dropped repeat is a lost message *type*, not a
    duplicate.

``auto`` (default)
    Try ``monitor``; fall back to ``dbus`` if the socket cannot be opened.

Known limitation
----------------
This captures **legacy** advertisements. The ASTM long-range profile uses BT5
extended advertising on the Coded PHY, which the Pi's CYW43455 is not known to
receive. Treat onboard capture as complementary to a Sniffle dongle or a
DroneScout receiver, not a replacement.
"""

import logging
import os
import socket
import struct
import threading

from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

_logger = logging.getLogger(__name__)

# --- BlueZ / HCI constants ------------------------------------------------

AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_CHANNEL_MONITOR = 2
HCI_DEV_NONE = 0xFFFF

# struct hci_mon_hdr { __le16 opcode; __le16 index; __le16 len; }
HCI_MON_HDR_LEN = 6
HCI_MON_EVENT_PKT = 0x0003

HCI_EVENT_LE_META = 0x3E
LE_ADVERTISING_REPORT = 0x02
LE_EXTENDED_ADVERTISING_REPORT = 0x0D

BLUEZ_SERVICE = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"

# 16-bit ASTM UUID 0xFFFA as BlueZ spells it on D-Bus.
ASTM_UUID_DBUS = "0000fffa-0000-1000-8000-00805f9b34fb"

DEFAULT_ADAPTER = "hci0"


def parse_bluez_feed_url(feed_url: str) -> dict:
    """Parse a ``ble+hci://`` FEED_URL.

    Examples
    --------
    ``ble+hci://hci0``
    ``ble+hci://hci0?reader=monitor&rssi=-95``
    """
    parsed = urlparse(feed_url)
    path = (parsed.path or "").strip()
    if path.startswith("//"):
        path = path[2:]
    adapter = parsed.hostname or path.strip("/") or DEFAULT_ADAPTER
    if adapter == "auto":
        adapter = DEFAULT_ADAPTER

    qs = parse_qs(parsed.query or "")
    reader = qs.get("reader", ["auto"])[0].lower()
    if reader not in {"auto", "monitor", "dbus"}:
        _logger.warning("Unknown BLE reader %r, using 'auto'", reader)
        reader = "auto"

    rssi_raw = qs.get("rssi", [None])[0]
    duplicates = qs.get("duplicates", ["1"])[0].lower() in {"1", "true", "yes"}

    return {
        "adapter": adapter,
        "reader": reader,
        "rssi_threshold": int(rssi_raw) if rssi_raw is not None else None,
        "duplicates": duplicates,
    }


def adapter_index(adapter: str) -> int:
    """``hci0`` -> ``0``. Used to filter monitor traffic to one controller."""
    digits = "".join(ch for ch in adapter if ch.isdigit())
    return int(digits) if digits else 0


def format_mac(addr_le: bytes) -> str:
    """HCI reports addresses little-endian; render them the human way."""
    return ":".join(f"{b:02X}" for b in reversed(addr_le[:6]))


def bind_hci_monitor(sock: socket.socket) -> None:
    """Bind ``sock`` to the HCI monitor channel.

    CPython's ``socket.bind()`` for ``BTPROTO_HCI`` accepts only ``(device_id,)``
    on current builds -- passing a channel raises "bind(): wrong format" -- so it
    cannot select ``HCI_CHANNEL_MONITOR`` at all. Try the two-tuple first in case
    the interpreter does support it, then fall back to calling ``bind(2)``
    directly with a proper ``struct sockaddr_hci``.

    Raises ``OSError`` if the bind fails (typically missing ``CAP_NET_RAW``).
    """
    try:
        sock.bind((HCI_DEV_NONE, HCI_CHANNEL_MONITOR))
        return
    except OSError:
        pass  # interpreter lacks channel support; fall through to ctypes

    import ctypes  # pylint: disable=import-outside-toplevel

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    # struct sockaddr_hci { sa_family_t family; unsigned short dev, channel; }
    addr = struct.pack("<HHH", AF_BLUETOOTH, HCI_DEV_NONE, HCI_CHANNEL_MONITOR)
    if libc.bind(sock.fileno(), addr, len(addr)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


# --- HCI advertising report parsing ---------------------------------------


def parse_le_advertising_report(params: bytes) -> List[Tuple[str, bytes, Optional[int]]]:
    """Decode an LE Advertising Report subevent body.

    Returns ``[(mac, adv_data, rssi), ...]``. Malformed or truncated reports
    yield nothing rather than raising -- this runs on radio input.
    """
    out: List[Tuple[str, bytes, Optional[int]]] = []
    if len(params) < 2:
        return out

    num_reports = params[1]
    pos = 2
    for _ in range(num_reports):
        # event_type(1) addr_type(1) addr(6) data_len(1)
        if pos + 9 > len(params):
            break
        addr = params[pos + 2 : pos + 8]
        data_len = params[pos + 8]
        pos += 9
        if pos + data_len > len(params):
            break
        adv_data = params[pos : pos + data_len]
        pos += data_len
        rssi = None
        if pos < len(params):
            rssi = struct.unpack("b", params[pos : pos + 1])[0]
            pos += 1
        out.append((format_mac(addr), adv_data, rssi))
    return out


def parse_le_extended_advertising_report(
    params: bytes,
) -> List[Tuple[str, bytes, Optional[int]]]:
    """Decode an LE Extended Advertising Report subevent body (BT5)."""
    out: List[Tuple[str, bytes, Optional[int]]] = []
    if len(params) < 2:
        return out

    num_reports = params[1]
    pos = 2
    for _ in range(num_reports):
        # event_type(2) addr_type(1) addr(6) primary_phy(1) secondary_phy(1)
        # adv_sid(1) tx_power(1) rssi(1) periodic_interval(2)
        # direct_addr_type(1) direct_addr(6) data_len(1)
        if pos + 24 > len(params):
            break
        addr = params[pos + 3 : pos + 9]
        rssi = struct.unpack("b", params[pos + 13 : pos + 14])[0]
        data_len = params[pos + 23]
        pos += 24
        if pos + data_len > len(params):
            break
        adv_data = params[pos : pos + data_len]
        pos += data_len
        out.append((format_mac(addr), adv_data, rssi))
    return out


def parse_monitor_packet(packet: bytes, index: int) -> List[Tuple[str, bytes, Optional[int]]]:
    """Extract advertising reports from one HCI monitor frame.

    ``index`` restricts decoding to a single controller, so a box with more than
    one adapter does not attribute another radio's traffic to this sensor.
    """
    if len(packet) < HCI_MON_HDR_LEN:
        return []

    opcode, pkt_index, length = struct.unpack_from("<HHH", packet, 0)
    if opcode != HCI_MON_EVENT_PKT or pkt_index != index:
        return []

    body = packet[HCI_MON_HDR_LEN : HCI_MON_HDR_LEN + length]
    # HCI event: event_code(1) param_len(1) params...
    if len(body) < 3 or body[0] != HCI_EVENT_LE_META:
        return []

    params = body[2:]
    if not params:
        return []

    subevent = params[0]
    if subevent == LE_ADVERTISING_REPORT:
        return parse_le_advertising_report(params)
    if subevent == LE_EXTENDED_ADVERTISING_REPORT:
        return parse_le_extended_advertising_report(params)
    return []


# --- Capture ---------------------------------------------------------------


class BlueZSniffer:
    """Capture ASTM F3411 Remote ID advertisements via a stock BlueZ adapter."""

    def __init__(
        self,
        on_packet: Callable,
        adapter: str = DEFAULT_ADAPTER,
        reader: str = "auto",
        rssi_threshold: Optional[int] = None,
        duplicates: bool = True,
    ):
        self.on_packet = on_packet
        self.adapter = adapter or DEFAULT_ADAPTER
        self.reader = reader
        self.rssi_threshold = rssi_threshold
        self.duplicates = duplicates

        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._sock: Optional[socket.socket] = None
        self._loop = None
        self._active_reader: Optional[str] = None

    # -- reader: HCI monitor tap -------------------------------------------

    def _open_monitor_socket(self) -> Optional[socket.socket]:
        """Open a passive HCI monitor socket, or return None if not permitted."""
        try:
            sock = socket.socket(
                AF_BLUETOOTH, socket.SOCK_RAW | socket.SOCK_CLOEXEC, BTPROTO_HCI
            )
        except (OSError, AttributeError) as exc:
            _logger.debug("HCI monitor socket unavailable: %s", exc)
            return None

        try:
            bind_hci_monitor(sock)
        except OSError as exc:
            sock.close()
            _logger.debug(
                "Cannot bind HCI monitor channel (%s); CAP_NET_RAW is required", exc
            )
            return None

        return sock

    def _run_monitor(self) -> None:
        from dronecot import ble_parse  # pylint: disable=import-outside-toplevel

        index = adapter_index(self.adapter)
        sock = self._sock
        if sock is None:
            return
        sock.settimeout(1.0)

        while not self._stop.is_set():
            try:
                packet = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop.is_set():
                    break
                _logger.debug("HCI monitor read error: %s", exc)
                continue

            for mac, adv_data, rssi in parse_monitor_packet(packet, index):
                self._emit(ble_parse, adv_data, mac, rssi)

    def _emit(self, ble_parse, adv_data: bytes, mac: str, rssi: Optional[int]) -> None:
        """Extract ODID from an advertisement and hand it upstream."""
        if self.rssi_threshold is not None and rssi is not None:
            if rssi < self.rssi_threshold:
                return

        pack = ble_parse.extract_odid_from_adv_data(adv_data)
        if not pack:
            return

        meta: Dict = {"type": "BLE legacy (BlueZ)", "MAC address": mac}
        if rssi is not None:
            meta["RSSI"] = rssi
        self.on_packet(pack, meta)

    # -- reader: BlueZ D-Bus ServiceData ------------------------------------

    def _handle_dbus_properties(self, address: Optional[str], props: dict) -> None:
        from dronecot import ble_parse  # pylint: disable=import-outside-toplevel

        service_data = props.get("ServiceData")
        if not service_data:
            return

        raw = None
        for uuid, value in service_data.items():
            if str(uuid).lower() == ASTM_UUID_DBUS:
                raw = bytes(bytearray(value))
                break
        if raw is None:
            return

        rssi = props.get("RSSI")
        rssi = int(rssi) if rssi is not None else None
        if self.rssi_threshold is not None and rssi is not None:
            if rssi < self.rssi_threshold:
                return

        # BlueZ hands back the service-data payload with the 16-bit UUID already
        # stripped; put it back so the shared AD parser sees its usual layout.
        pack = ble_parse.parse_odid_service_data(ble_parse.ASTM_BLE_UUID + raw)
        if not pack:
            return

        meta: Dict = {"type": "BLE legacy (BlueZ)"}
        if address:
            meta["MAC address"] = str(address).upper()
        if rssi is not None:
            meta["RSSI"] = rssi
        self.on_packet(pack, meta)

    def _run_dbus(self) -> None:
        """Drive a continuous LE scan and, on the dbus reader, decode from it."""
        try:
            import dbus  # pylint: disable=import-outside-toplevel
            import dbus.mainloop.glib  # pylint: disable=import-outside-toplevel
            from gi.repository import GLib  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise ImportError(
                "BlueZ capture requires python3-dbus and python3-gi "
                "(Debian: apt install python3-dbus python3-gi)"
            ) from exc

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        adapter_path = f"/org/bluez/{self.adapter}"

        adapter = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE, adapter_path), ADAPTER_IFACE
        )

        # Transport 'le' keeps Classic (and therefore an active PAN) untouched.
        # DuplicateData asks BlueZ to report repeated advertisement payloads
        # rather than coalescing them -- essential when each repeat may carry a
        # different ODID message type.
        discovery_filter = {
            "Transport": "le",
            "DuplicateData": dbus.Boolean(self.duplicates),
        }
        if self.rssi_threshold is not None:
            discovery_filter["RSSI"] = dbus.Int16(self.rssi_threshold)

        try:
            adapter.SetDiscoveryFilter(discovery_filter)
        except dbus.DBusException as exc:
            _logger.warning("SetDiscoveryFilter failed (%s); scanning unfiltered", exc)

        try:
            adapter.StartDiscovery()
        except dbus.DBusException as exc:
            # Another client may already be discovering, which is fine -- the
            # radio is scanning either way and that is all the tap needs.
            _logger.info("StartDiscovery: %s (continuing)", exc)

        if self._active_reader == "dbus":
            self._connect_dbus_signals(bus)

        self._loop = GLib.MainLoop()
        try:
            self._loop.run()
        finally:
            try:
                adapter.StopDiscovery()
            except Exception:  # pylint: disable=broad-except
                pass

    def _connect_dbus_signals(self, bus) -> None:
        """Subscribe to advertisement properties for the D-Bus reader."""

        def on_interfaces_added(_path, interfaces):
            props = interfaces.get(DEVICE_IFACE)
            if props:
                self._handle_dbus_properties(props.get("Address"), props)

        def on_properties_changed(interface, changed, _invalidated, path=None):
            if interface != DEVICE_IFACE:
                return
            address = None
            if path:
                # /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
                tail = str(path).rsplit("/", 1)[-1]
                if tail.startswith("dev_"):
                    address = tail[4:].replace("_", ":")
            self._handle_dbus_properties(address, changed)

        bus.add_signal_receiver(
            on_interfaces_added,
            dbus_interface="org.freedesktop.DBus.ObjectManager",
            signal_name="InterfacesAdded",
        )
        bus.add_signal_receiver(
            on_properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            arg0=DEVICE_IFACE,
            path_keyword="path",
        )

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()

        if self.reader in {"auto", "monitor"}:
            self._sock = self._open_monitor_socket()
            if self._sock is None and self.reader == "monitor":
                raise IOError(
                    "HCI monitor socket unavailable: dronecot needs CAP_NET_RAW "
                    "for reader=monitor (systemd: AmbientCapabilities=CAP_NET_RAW)"
                )

        self._active_reader = "monitor" if self._sock is not None else "dbus"
        if self.reader == "dbus":
            self._active_reader = "dbus"
            if self._sock is not None:
                self._sock.close()
                self._sock = None

        # The scan driver runs either way: the monitor tap is passive and sees
        # nothing unless the controller is actually scanning.
        self._spawn(self._run_dbus, "dronecot-ble-scan")
        if self._active_reader == "monitor":
            self._spawn(self._run_monitor, "dronecot-ble-monitor")

        _logger.info(
            "BlueZ Remote ID capture started on %s (reader=%s)",
            self.adapter,
            self._active_reader,
        )

    def _spawn(self, target: Callable, name: str) -> None:
        thread = threading.Thread(target=target, daemon=True, name=name)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            try:
                self._loop.quit()
            except Exception:  # pylint: disable=broad-except
                pass
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads = []
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
