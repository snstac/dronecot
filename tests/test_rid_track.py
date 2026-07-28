#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for per-transmitter ODID track aggregation.

These exercise the case the existing fixtures miss entirely: BLE legacy
advertising, where each frame carries ONE 25-byte ODID message and the serial,
the position and the operator location arrive separately.
"""

import struct
import unittest

from dronecot import ble_parse, functions, rid_normalize, rid_track


ODID_MESSAGE_SIZE = 25
PROTO_VERSION = 2

# A real ASTM F3411 advertisement captured off the air with btmon on an AryaOS
# box, from a BlueMark DroneBeacon DB120 transmitting nearby. Kept verbatim
# because every synthetic fixture in this repo is a message PACK, which is not
# what a BLE legacy transmitter actually sends.
#   1e        AD length
#   16        AD type: Service Data - 16-bit UUID
#   fa ff     UUID 0xFFFA (ASTM F3411)
#   0d        ASTM application code
#   22        message counter
#   42 ...    ODID message: type 4 (System), version 2
CAPTURED_DB120_AD = bytes.fromhex(
    "1e16faff0d2242008eb78116f15bfcb601000000000000004c08eec73b0e00"
)


def _basic_id_message(serial: str, id_type: int = 1, ua_type: int = 2) -> bytes:
    """Build a single ODID BasicID message (type 0)."""
    msg = bytearray(ODID_MESSAGE_SIZE)
    msg[0] = (0 << 4) | PROTO_VERSION
    msg[1] = (id_type << 4) | ua_type
    msg[2:22] = serial.encode("ascii").ljust(20, b"\x00")
    return bytes(msg)


def _location_message(lat: float, lon: float) -> bytes:
    """Build a single ODID Location message (type 1)."""
    msg = bytearray(ODID_MESSAGE_SIZE)
    msg[0] = (1 << 4) | PROTO_VERSION
    msg[1] = 0x20  # Status=2 (Airborne)
    msg[2] = 90  # Direction
    msg[3] = 10  # SpeedHorizontal
    msg[4] = 0  # SpeedVertical
    msg[5:9] = struct.pack("i", int(lat * 1e7))
    msg[9:13] = struct.pack("i", int(lon * 1e7))
    msg[13:15] = struct.pack("H", 2000 + 200)  # AltitudeBaro -> 100.0 m
    msg[15:17] = struct.pack("H", 2000 + 200)  # AltitudeGeo  -> 100.0 m
    msg[17:19] = struct.pack("H", 2000 + 100)  # Height       ->  50.0 m
    return bytes(msg)


def _system_message(op_lat: float, op_lon: float) -> bytes:
    """Build a single ODID System message (type 4)."""
    msg = bytearray(ODID_MESSAGE_SIZE)
    msg[0] = (4 << 4) | PROTO_VERSION
    msg[1] = 0x01
    msg[2:6] = struct.pack("i", int(op_lat * 1e7))
    msg[6:10] = struct.pack("i", int(op_lon * 1e7))
    return bytes(msg)


def _rid(msg: bytes, mac: str, rssi: int = -70) -> dict:
    """Normalize a single ODID message the way a BLE worker would."""
    return rid_normalize.bytes_to_rid_dict(
        msg, {"MAC address": mac, "RSSI": rssi, "type": "BLE legacy"}
    )


class TestCapturedAdvertisement(unittest.TestCase):
    """The real DB120 frame must parse through the existing BLE chain."""

    def test_extracts_odid_payload(self):
        pack = ble_parse.extract_odid_from_adv_data(CAPTURED_DB120_AD)
        self.assertIsNotNone(pack)
        self.assertGreaterEqual(len(pack), ODID_MESSAGE_SIZE)
        self.assertEqual(pack[0] >> 4, 4, "expected an ODID System message")
        self.assertEqual(pack[0] & 0x0F, PROTO_VERSION)

    def test_system_only_message_has_no_uas_position(self):
        pack = ble_parse.extract_odid_from_adv_data(CAPTURED_DB120_AD)
        rid = rid_normalize.bytes_to_rid_dict(pack, {"MAC address": "AA:BB:CC:DD:EE:FF"})
        self.assertIsNotNone(rid)
        # A System message carries neither serial nor UAS position -- which is
        # exactly why aggregation is required.
        self.assertNotIn("BasicID", rid)
        self.assertIsNone(rid.get("Latitude"))


class TestODIDAggregator(unittest.TestCase):
    def test_rotating_messages_merge_into_one_track(self):
        agg = rid_track.ODIDAggregator()
        mac = "DF:72:11:D2:6B:95"

        # BasicID first: no position yet, so nothing renderable.
        self.assertIsNone(agg.update(_rid(_basic_id_message("SERIAL123"), mac)))

        # Location next: now the track has both serial and position.
        merged = agg.update(_rid(_location_message(37.7749, -122.4194), mac))
        self.assertIsNotNone(merged)
        self.assertEqual(merged["BasicID"], "SERIAL123")
        self.assertAlmostEqual(merged["Latitude"], 37.7749, places=5)
        self.assertAlmostEqual(merged["Longitude"], -122.4194, places=5)

        # System adds the operator location without losing the rest.
        merged = agg.update(_rid(_system_message(37.80, -122.40), mac))
        self.assertEqual(merged["BasicID"], "SERIAL123")
        self.assertAlmostEqual(merged["Latitude"], 37.7749, places=5)
        self.assertAlmostEqual(merged["OperatorLatitude"], 37.80, places=5)
        self.assertEqual(len(agg), 1)

    def test_two_transmitters_stay_separate(self):
        """The regression that mattered: distinct drones must not collapse."""
        agg = rid_track.ODIDAggregator()
        mac_a, mac_b = "AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"

        agg.update(_rid(_basic_id_message("DRONE-A"), mac_a))
        agg.update(_rid(_basic_id_message("DRONE-B"), mac_b))

        merged_a = agg.update(_rid(_location_message(10.0, 20.0), mac_a))
        merged_b = agg.update(_rid(_location_message(30.0, 40.0), mac_b))

        self.assertEqual(merged_a["BasicID"], "DRONE-A")
        self.assertEqual(merged_b["BasicID"], "DRONE-B")
        self.assertAlmostEqual(merged_a["Latitude"], 10.0, places=5)
        self.assertAlmostEqual(merged_b["Latitude"], 30.0, places=5)
        self.assertEqual(len(agg), 2)

    def test_metadata_merges_rather_than_clobbers(self):
        agg = rid_track.ODIDAggregator()
        mac = "AA:BB:CC:DD:EE:FF"

        agg.update(_rid(_basic_id_message("SERIAL123"), mac, rssi=-55))
        merged = agg.update(
            rid_normalize.bytes_to_rid_dict(
                _location_message(1.0, 2.0), {"MAC address": mac}
            )
        )
        # RSSI came from an earlier frame that had it; it must survive.
        self.assertEqual(merged["data"]["RSSI"], -55)
        self.assertEqual(merged["data"]["MAC address"], mac)

    def test_ttl_expires_stale_tracks(self):
        agg = rid_track.ODIDAggregator(ttl=0.0001)
        mac = "AA:BB:CC:DD:EE:FF"
        agg.update(_rid(_basic_id_message("SERIAL123"), mac))
        self.assertEqual(len(agg), 1)

        import time as _time

        _time.sleep(0.01)
        self.assertEqual(agg.prune(), 1)
        self.assertEqual(len(agg), 0)

    def test_id_grace_holds_position_only_track(self):
        """Avoid two TAK markers for one aircraft.

        Rendering a Location before its BasicID arrives emits CoT under a
        MAC-derived UID, then switches to the real serial moments later.
        Measured against a live DroneBeacon DB120: without the grace period a
        single aircraft produced BOTH 'RID.MAC-DF7211D26B95.uas' and
        'RID.1787F04BM24010011195.uas'.
        """
        agg = rid_track.ODIDAggregator(id_grace=30.0)
        mac = "DF:72:11:D2:6B:95"

        # Position first, serial not yet heard -> held back.
        self.assertIsNone(agg.update(_rid(_location_message(37.7, -122.4), mac)))

        # Serial arrives -> now it renders, under the real serial.
        merged = agg.update(_rid(_basic_id_message("SERIAL123"), mac))
        self.assertIsNotNone(merged)
        self.assertEqual(merged["BasicID"], "SERIAL123")
        self.assertEqual(
            functions._rid_identity(merged)[0], "SERIAL123"
        )

    def test_id_grace_expires_so_unknown_drones_still_appear(self):
        """An unidentified drone must still reach the map."""
        agg = rid_track.ODIDAggregator(id_grace=0.001)
        mac = "AA:BB:CC:DD:EE:FF"
        agg.update(_rid(_location_message(37.7, -122.4), mac))

        import time as _time

        _time.sleep(0.01)
        merged = agg.update(_rid(_location_message(37.71, -122.41), mac))
        self.assertIsNotNone(merged, "grace expired; track must render anyway")
        self.assertEqual(
            functions._rid_identity(merged)[0], "MAC-AABBCCDDEEFF"
        )

    def test_id_grace_disabled_renders_immediately(self):
        agg = rid_track.ODIDAggregator(id_grace=0)
        merged = agg.update(_rid(_location_message(1.0, 2.0), "AA:BB:CC:DD:EE:FF"))
        self.assertIsNotNone(merged)

    def test_empty_aggregator_is_truthy(self):
        """__len__ would otherwise make a fresh aggregator falsy, so the natural
        `if aggregator:` would silently skip aggregation forever."""
        agg = rid_track.ODIDAggregator()
        self.assertEqual(len(agg), 0)
        self.assertTrue(agg)
        self.assertTrue(bool(agg))

    def test_max_tracks_is_bounded(self):
        agg = rid_track.ODIDAggregator(max_tracks=4)
        for i in range(40):
            agg.update(_rid(_basic_id_message(f"SER{i}"), f"AA:BB:CC:DD:EE:{i:02X}"))
        self.assertLessEqual(len(agg), 4)

    def test_message_pack_passes_through_unchanged(self):
        """0xF packs already carry everything; aggregation must not alter them."""
        agg = rid_track.ODIDAggregator()
        pack = (
            bytes([0xF0, ODID_MESSAGE_SIZE, 2])
            + _basic_id_message("PACKED1")
            + _location_message(5.0, 6.0)
        )
        rid = rid_normalize.bytes_to_rid_dict(pack, {"MAC address": "AA:BB:CC:DD:EE:FF"})
        merged = agg.update(rid)
        self.assertEqual(merged["BasicID"], "PACKED1")
        self.assertAlmostEqual(merged["Latitude"], 5.0, places=5)

    def test_record_without_identity_passes_through(self):
        agg = rid_track.ODIDAggregator()
        rid = rid_normalize.bytes_to_rid_dict(_location_message(7.0, 8.0), {})
        merged = agg.update(rid)
        self.assertIsNotNone(merged, "un-keyable records must not be swallowed")
        self.assertAlmostEqual(merged["Latitude"], 7.0, places=5)


class TestFieldPadding(unittest.TestCase):
    """ODID pads fixed-width ASCII fields with NUL, which is illegal in XML.

    Serials shorter than the 20-byte field used to carry their padding all the
    way into the CoT UID, producing a document that would not reparse. Every
    shipped fixture happens to use a full-width 20-character serial, which is
    why this went unnoticed.
    """

    def test_short_serial_is_not_nul_padded(self):
        rid = _rid(_basic_id_message("SHORTSN"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(rid["BasicID"], "SHORTSN")
        self.assertNotIn("\x00", rid["BasicID"])

    def test_cot_xml_reparses(self):
        import xml.etree.ElementTree as ET

        pack = (
            bytes([0xF0, ODID_MESSAGE_SIZE, 2])
            + _basic_id_message("SHORTSN")
            + _location_message(37.7, -122.4)
        )
        rid = rid_normalize.bytes_to_rid_dict(pack, {"MAC address": "AA:BB:CC:DD:EE:FF"})
        event = functions.rid_uas_to_cot_xml(rid, {})
        raw = ET.tostring(event)
        self.assertNotIn(b"\x00", raw)
        ET.fromstring(raw)  # must not raise
        self.assertEqual(event.get("uid"), "RID.SHORTSN.uas")


class TestMaclessSources(unittest.TestCase):
    """Serial/MAVLink receivers report no MAC at all.

    Measured on a live DroneScout Bridge: 57 correctly identified events
    alongside 3 rendered under the shared ``Unknown-BasicID_0`` placeholder.

    These records must NOT be aggregated on the feed -- one receiver reports
    many aircraft, so a feed key would merge distinct drones. Instead they pass
    through, and only the rendered UID falls back to the feed so contacts from
    different receivers stay distinct.
    """

    @staticmethod
    def _serial_rid(msg, sensor="dronescout"):
        """Normalize a message the way a serial worker does: NO MAC address."""
        return rid_normalize.bytes_to_rid_dict(
            msg, {"sensor_id": sensor, "type": "MAVLink"}
        )

    def test_macless_without_serial_uses_feed_not_placeholder(self):
        """The fix: never render under the shared placeholder UID."""
        rid = self._serial_rid(_system_message(51.5, -0.12))
        uid, mac = functions._rid_identity(rid)
        self.assertIsNone(mac)
        self.assertEqual(uid, "FEED-dronescout")
        self.assertNotEqual(uid, "Unknown-BasicID_0")

    def test_different_receivers_stay_distinct(self):
        a = functions._rid_identity(self._serial_rid(_system_message(1.0, 2.0), "rx-a"))[0]
        b = functions._rid_identity(self._serial_rid(_system_message(3.0, 4.0), "rx-b"))[0]
        self.assertNotEqual(a, b)

    def test_serial_wins_over_feed_in_uid(self):
        rid = self._serial_rid(_basic_id_message("SERIAL9"))
        self.assertEqual(functions._rid_identity(rid)[0], "SERIAL9")

    def test_feed_is_NOT_used_as_an_aggregation_key(self):
        """Guard against merging distinct aircraft from one multi-drone feed."""
        rid = self._serial_rid(_location_message(51.5, -0.12))
        self.assertIsNone(
            rid_track.track_key(rid),
            "a MAC-less, serial-less record must not be keyed on its feed",
        )

    def test_mac_still_wins_when_present(self):
        rid = _rid(_location_message(1.0, 2.0), "AA:BB:CC:DD:EE:FF")
        rid["data"]["sensor_id"] = "dronescout"
        self.assertEqual(rid_track.track_key(rid)[0], "mac")


class TestRidIdentity(unittest.TestCase):
    def test_missing_basic_id_falls_back_to_mac(self):
        rid = _rid(_location_message(1.0, 2.0), "DF:72:11:D2:6B:95")
        uasid, mac = functions._rid_identity(rid)
        self.assertEqual(mac, "DF:72:11:D2:6B:95")
        self.assertEqual(uasid, "MAC-DF7211D26B95")
        self.assertNotEqual(uasid, "Unknown-BasicID_0")

    def test_distinct_macs_yield_distinct_uids(self):
        a = functions._rid_identity(_rid(_location_message(1.0, 2.0), "AA:AA:AA:AA:AA:AA"))[0]
        b = functions._rid_identity(_rid(_location_message(3.0, 4.0), "BB:BB:BB:BB:BB:BB"))[0]
        self.assertNotEqual(a, b)

    def test_basic_id_wins_when_present(self):
        rid = _rid(_basic_id_message("SERIAL123"), "AA:BB:CC:DD:EE:FF")
        uasid, _ = functions._rid_identity(rid)
        self.assertEqual(uasid, "SERIAL123")

    def test_operator_cot_uid_uses_wireless_mac(self):
        """rid_op_to_cot_xml read the MAC from the wrong level before this fix."""
        rid = _rid(_system_message(37.8, -122.4), "DF:72:11:D2:6B:95")
        event = functions.rid_op_to_cot_xml(rid, {})
        self.assertIsNotNone(event)
        self.assertEqual(event.get("uid"), "op-DF:72:11:D2:6B:95")

    def test_no_identity_at_all_keeps_legacy_placeholder(self):
        uasid, mac = functions._rid_identity({"Latitude": 1.0, "Longitude": 2.0})
        self.assertIsNone(mac)
        self.assertEqual(uasid, "Unknown-BasicID_0")


if __name__ == "__main__":
    unittest.main()
