#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for BlueZ-based Bluetooth Remote ID capture.

The HCI decoding is exercised offline by synthesizing monitor frames around a
REAL ASTM F3411 advertisement captured with btmon on an AryaOS box, so these
run in CI with no Bluetooth adapter present.
"""

import struct
import unittest

from dronecot import ble_parse, bluez_capture


# Real BLE advertising payload from a BlueMark DroneBeacon DB120, captured off
# the air. AD length 0x1e, type 0x16 (Service Data), UUID 0xFFFA, app code 0x0D,
# message counter 0x22, then a 25-byte ODID System message (type 4, version 2).
CAPTURED_AD = bytes.fromhex(
    "1e16faff0d2242008eb78116f15bfcb601000000000000004c08eec73b0e00"
)
CAPTURED_MAC_LE = bytes.fromhex("95 6b d2 11 72 df".replace(" ", ""))
CAPTURED_MAC = "DF:72:11:D2:6B:95"


def _monitor_frame(event_params: bytes, index: int = 0) -> bytes:
    """Wrap HCI LE Meta event params in the monitor + HCI event headers."""
    hci_event = bytes([bluez_capture.HCI_EVENT_LE_META, len(event_params)]) + event_params
    header = struct.pack(
        "<HHH", bluez_capture.HCI_MON_EVENT_PKT, index, len(hci_event)
    )
    return header + hci_event


def _legacy_report(adv_data: bytes, mac_le: bytes, rssi: int) -> bytes:
    """Build an LE Advertising Report subevent body with one report."""
    return (
        bytes([bluez_capture.LE_ADVERTISING_REPORT, 1])
        + bytes([0x00, 0x01])  # event_type, addr_type
        + mac_le
        + bytes([len(adv_data)])
        + adv_data
        + struct.pack("b", rssi)
    )


def _extended_report(adv_data: bytes, mac_le: bytes, rssi: int) -> bytes:
    """Build an LE Extended Advertising Report subevent body with one report."""
    return (
        bytes([bluez_capture.LE_EXTENDED_ADVERTISING_REPORT, 1])
        + struct.pack("<H", 0x0000)  # event_type
        + bytes([0x01])  # addr_type
        + mac_le
        + bytes([0x01, 0x03, 0x00, 0x7F])  # primary/secondary phy, sid, tx_power
        + struct.pack("b", rssi)
        + struct.pack("<H", 0)  # periodic interval
        + bytes([0x00])  # direct addr type
        + bytes(6)  # direct addr
        + bytes([len(adv_data)])
        + adv_data
    )


class TestFeedUrl(unittest.TestCase):
    def test_defaults(self):
        feed = bluez_capture.parse_bluez_feed_url("ble+hci://hci0")
        self.assertEqual(feed["adapter"], "hci0")
        self.assertEqual(feed["reader"], "auto")
        self.assertIsNone(feed["rssi_threshold"])
        self.assertTrue(feed["duplicates"])

    def test_options(self):
        feed = bluez_capture.parse_bluez_feed_url(
            "ble+hci://hci1?reader=monitor&rssi=-95&duplicates=0"
        )
        self.assertEqual(feed["adapter"], "hci1")
        self.assertEqual(feed["reader"], "monitor")
        self.assertEqual(feed["rssi_threshold"], -95)
        self.assertFalse(feed["duplicates"])

    def test_bare_and_auto_fall_back_to_hci0(self):
        self.assertEqual(bluez_capture.parse_bluez_feed_url("ble+hci://")["adapter"], "hci0")
        self.assertEqual(
            bluez_capture.parse_bluez_feed_url("ble+hci://auto")["adapter"], "hci0"
        )

    def test_unknown_reader_falls_back(self):
        feed = bluez_capture.parse_bluez_feed_url("ble+hci://hci0?reader=bogus")
        self.assertEqual(feed["reader"], "auto")

    def test_adapter_index(self):
        self.assertEqual(bluez_capture.adapter_index("hci0"), 0)
        self.assertEqual(bluez_capture.adapter_index("hci3"), 3)
        self.assertEqual(bluez_capture.adapter_index("nonsense"), 0)


class TestMonitorDecoding(unittest.TestCase):
    def test_decodes_captured_legacy_advertisement(self):
        frame = _monitor_frame(_legacy_report(CAPTURED_AD, CAPTURED_MAC_LE, -67))
        reports = bluez_capture.parse_monitor_packet(frame, 0)

        self.assertEqual(len(reports), 1)
        mac, adv_data, rssi = reports[0]
        self.assertEqual(mac, CAPTURED_MAC)
        self.assertEqual(rssi, -67)
        self.assertEqual(adv_data, CAPTURED_AD)

        # And the shared parser still finds the ODID payload in it.
        pack = ble_parse.extract_odid_from_adv_data(adv_data)
        self.assertIsNotNone(pack)
        self.assertEqual(pack[0] >> 4, 4)  # System message

    def test_decodes_extended_advertisement(self):
        frame = _monitor_frame(_extended_report(CAPTURED_AD, CAPTURED_MAC_LE, -80))
        reports = bluez_capture.parse_monitor_packet(frame, 0)

        self.assertEqual(len(reports), 1)
        mac, adv_data, rssi = reports[0]
        self.assertEqual(mac, CAPTURED_MAC)
        self.assertEqual(rssi, -80)
        self.assertEqual(adv_data, CAPTURED_AD)

    def test_ignores_other_adapters(self):
        frame = _monitor_frame(_legacy_report(CAPTURED_AD, CAPTURED_MAC_LE, -67), index=1)
        self.assertEqual(bluez_capture.parse_monitor_packet(frame, 0), [])

    def test_ignores_non_event_packets(self):
        header = struct.pack("<HHH", 0x0002, 0, 3)  # HCI_MON_COMMAND_PKT
        self.assertEqual(bluez_capture.parse_monitor_packet(header + b"\x01\x02\x03", 0), [])

    def test_truncated_input_does_not_raise(self):
        """Radio input: malformed frames must be dropped, never crash the reader."""
        frame = _monitor_frame(_legacy_report(CAPTURED_AD, CAPTURED_MAC_LE, -67))
        for cut in range(len(frame)):
            bluez_capture.parse_monitor_packet(frame[:cut], 0)
        self.assertEqual(bluez_capture.parse_monitor_packet(b"", 0), [])

    def test_multiple_reports_in_one_event(self):
        body = (
            bytes([bluez_capture.LE_ADVERTISING_REPORT, 2])
            + bytes([0x00, 0x01])
            + CAPTURED_MAC_LE
            + bytes([len(CAPTURED_AD)])
            + CAPTURED_AD
            + struct.pack("b", -60)
            + bytes([0x00, 0x01])
            + bytes.fromhex("aabbccddeeff")
            + bytes([len(CAPTURED_AD)])
            + CAPTURED_AD
            + struct.pack("b", -90)
        )
        reports = bluez_capture.parse_monitor_packet(_monitor_frame(body), 0)
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0][2], -60)
        self.assertEqual(reports[1][2], -90)
        self.assertEqual(reports[1][0], "FF:EE:DD:CC:BB:AA")


class TestEmit(unittest.TestCase):
    """The path from an advertisement to a normalized (pack, meta) callback."""

    def _sniffer(self, **kwargs):
        self.packets = []
        return bluez_capture.BlueZSniffer(
            on_packet=lambda pack, meta: self.packets.append((pack, meta)), **kwargs
        )

    def test_emits_odid_with_metadata(self):
        sniffer = self._sniffer()
        sniffer._emit(ble_parse, CAPTURED_AD, CAPTURED_MAC, -67)

        self.assertEqual(len(self.packets), 1)
        pack, meta = self.packets[0]
        self.assertEqual(pack[0] >> 4, 4)
        self.assertEqual(meta["MAC address"], CAPTURED_MAC)
        self.assertEqual(meta["RSSI"], -67)
        self.assertEqual(meta["type"], "BLE legacy (BlueZ)")

    def test_non_odid_advertisement_is_ignored(self):
        sniffer = self._sniffer()
        # A plain "Flags" AD structure, nothing to do with Remote ID.
        sniffer._emit(ble_parse, bytes([0x02, 0x01, 0x06]), CAPTURED_MAC, -50)
        self.assertEqual(self.packets, [])

    def test_rssi_threshold_filters_weak_frames(self):
        sniffer = self._sniffer(rssi_threshold=-70)
        sniffer._emit(ble_parse, CAPTURED_AD, CAPTURED_MAC, -90)
        self.assertEqual(self.packets, [])
        sniffer._emit(ble_parse, CAPTURED_AD, CAPTURED_MAC, -60)
        self.assertEqual(len(self.packets), 1)


class TestDbusServiceData(unittest.TestCase):
    def test_service_data_is_rewrapped_for_the_shared_parser(self):
        """BlueZ strips the UUID; we must put it back before parsing."""
        packets = []
        sniffer = bluez_capture.BlueZSniffer(
            on_packet=lambda pack, meta: packets.append((pack, meta))
        )

        # ServiceData value is everything after the 16-bit UUID.
        service_value = CAPTURED_AD[4:]
        sniffer._handle_dbus_properties(
            CAPTURED_MAC,
            {"ServiceData": {bluez_capture.ASTM_UUID_DBUS: service_value}, "RSSI": -72},
        )

        self.assertEqual(len(packets), 1)
        pack, meta = packets[0]
        self.assertEqual(pack[0] >> 4, 4)
        self.assertEqual(meta["MAC address"], CAPTURED_MAC)
        self.assertEqual(meta["RSSI"], -72)

    def test_other_service_uuids_ignored(self):
        packets = []
        sniffer = bluez_capture.BlueZSniffer(
            on_packet=lambda pack, meta: packets.append((pack, meta))
        )
        sniffer._handle_dbus_properties(
            CAPTURED_MAC,
            {"ServiceData": {"0000180f-0000-1000-8000-00805f9b34fb": b"\x64"}},
        )
        self.assertEqual(packets, [])

    def test_no_service_data_is_ignored(self):
        packets = []
        sniffer = bluez_capture.BlueZSniffer(
            on_packet=lambda pack, meta: packets.append((pack, meta))
        )
        sniffer._handle_dbus_properties(CAPTURED_MAC, {"RSSI": -60})
        self.assertEqual(packets, [])


class TestRouting(unittest.TestCase):
    """`ble+hci` contains the substring `ble`, so branch order matters."""

    def _workers(self, feed_url):
        import asyncio
        import dronecot

        class _CliTool:  # minimal stand-in for pytak.CLITool
            def __init__(self):
                self.tx_queue = asyncio.Queue()

        async def build():
            return dronecot.create_tasks({"FEED_URL": feed_url}, _CliTool())

        return {type(t).__name__ for t in asyncio.run(build())}

    def test_ble_hci_routes_to_bluez_worker(self):
        names = self._workers("ble+hci://hci0")
        self.assertIn("BlueZWorker", names)
        self.assertNotIn("BleWorker", names)
        self.assertIn("RIDWorker", names)

    def test_plain_ble_still_routes_to_sniffle_worker(self):
        names = self._workers("ble://auto")
        self.assertIn("BleWorker", names)
        self.assertNotIn("BlueZWorker", names)


if __name__ == "__main__":
    unittest.main()
