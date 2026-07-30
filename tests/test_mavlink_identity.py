#!/usr/bin/env python3
# Copyright Sensors & Signals LLC https://www.snstac.com/
# SPDX-License-Identifier: Apache-2.0
"""Transmitter identity on the MAVLink serial feed (DroneScout Bridge).

Regression tests for operator tracks collapsing onto op-Unknown-BasicID_0.

Measured on a live box (aryaos-4f11, DroneScout DS110, dronecot 2.3.1), 30s of
CoT on the Mesh SA group, attributed by source IP:

    op-Unknown-BasicID_0          x62   <- every operator on ONE track
    RID.1787F04BM24010011195.uas  x54   correct
    op-1787F04BM24010011195       x54   correct

The aircraft UID resolved but the operator UID did not. Cause: the MAVLink path
called rid_normalize.odid_parsed_to_rid_dict directly and attached no ``data``
metadata at all, unlike the wireless path (bytes_to_rid_dict). With no MAC and no
sensor_id, a pack carrying only System/OperatorID had no transmitter identity to
key on, so functions._rid_identity fell all the way to Unknown-BasicID_0.

MAVLink OpenDroneID carries a 20-byte ``id_or_mac`` naming the transmitter. The
DS110 populates it on every pack -- measured 58 of 58, as
db:13:81:94:13:55 + 14 zero bytes -- and it is the only per-aircraft grouping key
a serial feed offers.
"""

import types
import unittest
from unittest import mock

from dronecot.classes import SerialWorker
from dronecot.functions import _rid_identity

# Exactly what the DS110 sent, including the 14 bytes of padding.
DS110_ID_OR_MAC = bytes.fromhex("db13819413550000000000000000000000000000")
DS110_MAC = "DB:13:81:94:13:55"


def _worker(sensor_id="dronescout"):
    """A SerialWorker with just enough state for the metadata helpers."""
    w = SerialWorker.__new__(SerialWorker)
    w.config = {"SENSOR_ID": sensor_id}
    return w


class IdOrMacTestCase(unittest.TestCase):
    def test_real_ds110_value_renders_as_mac(self):
        self.assertEqual(SerialWorker._id_or_mac_to_mac(DS110_ID_OR_MAC), DS110_MAC)

    def test_all_zeros_is_no_identity(self):
        self.assertIsNone(SerialWorker._id_or_mac_to_mac(bytes(20)))

    def test_absent_is_no_identity(self):
        self.assertIsNone(SerialWorker._id_or_mac_to_mac(None))

    def test_opaque_id_is_not_claimed_to_be_a_mac(self):
        """Payload past byte 6 means this is an ID string, not a MAC.

        Rendering it as one would put a wrong-looking value in the CoT UID, so it
        is left alone rather than guessed at.
        """
        self.assertIsNone(SerialWorker._id_or_mac_to_mac(b"SERIAL12345678901234"))

    def test_accepts_a_bare_six_byte_field(self):
        self.assertEqual(
            SerialWorker._id_or_mac_to_mac(bytes.fromhex("db13819413 55".replace(" ", ""))),
            DS110_MAC,
        )


class MavlinkMetaTestCase(unittest.TestCase):
    def test_meta_carries_identity_and_configured_sensor_id(self):
        meta = _worker()._mavlink_meta(DS110_ID_OR_MAC, payload_type="pack")
        self.assertEqual(meta["MAC address"], DS110_MAC)
        # Previously absent, so CoT was attributed to dronecot_<hostname> and you
        # could not tell which receiver saw a contact.
        self.assertEqual(meta["sensor_id"], "dronescout")
        self.assertEqual(meta["type"], "pack")

    def test_no_identity_still_yields_sensor_id(self):
        meta = _worker()._mavlink_meta(bytes(20))
        self.assertNotIn("MAC address", meta)
        self.assertEqual(meta["sensor_id"], "dronescout")


class PackIdentityTestCase(unittest.TestCase):
    """The actual regression: a pack with no BasicID must still identify itself."""

    def _pack(self, parsed):
        with mock.patch("dronecot.odid.message_pack_to_dict", return_value=parsed):
            return _worker()._mavlink_pack_to_parse_payload_schema(
                b"\x00" * 25, 1, DS110_ID_OR_MAC
            )

    def test_pack_without_basicid_gets_a_distinct_uid(self):
        rid = self._pack({"OperatorLatitude": 37.7, "OperatorLongitude": -122.4})
        uasid, mac = _rid_identity(rid)
        self.assertEqual(mac, DS110_MAC)
        # The bug: this was "Unknown-BasicID_0" for every transmitter in range.
        self.assertNotEqual(uasid, "Unknown-BasicID_0")
        self.assertEqual(uasid, "MAC-DB1381941355")

    def test_pack_with_basicid_prefers_the_real_serial(self):
        rid = self._pack({"UASID": "1787F04BM24010011195"})
        uasid, mac = _rid_identity(rid)
        self.assertEqual(uasid, "1787F04BM24010011195")
        self.assertEqual(mac, DS110_MAC)

    def test_two_transmitters_do_not_collapse(self):
        """The DS110 reports many aircraft over one port; they must stay distinct."""
        other = bytes.fromhex("aabbccddeeff" + "00" * 14)
        with mock.patch("dronecot.odid.message_pack_to_dict", return_value={}):
            a = _worker()._mavlink_pack_to_parse_payload_schema(
                b"\x00" * 25, 1, DS110_ID_OR_MAC
            )
            b = _worker()._mavlink_pack_to_parse_payload_schema(
                b"\x00" * 25, 1, other
            )
        self.assertNotEqual(_rid_identity(a)[0], _rid_identity(b)[0])


class SensorIdFallbackTestCase(unittest.TestCase):
    """_rid_identity looked for sensor_id only in data['data'].

    The MAC was already checked at both levels because "MQTT and serial feeds put
    it at the top level" -- the same is true of sensor_id, so that rung of the
    fallback silently never fired for those feeds.
    """

    def test_top_level_sensor_id_is_used(self):
        uasid, mac = _rid_identity({"sensor_id": "dronescout"})
        self.assertIsNone(mac)
        self.assertEqual(uasid, "FEED-dronescout")

    def test_nested_sensor_id_still_works(self):
        uasid, _ = _rid_identity({"data": {"sensor_id": "dronescout"}})
        self.assertEqual(uasid, "FEED-dronescout")

    def test_nothing_at_all_is_still_the_last_resort(self):
        uasid, _ = _rid_identity({})
        self.assertEqual(uasid, "Unknown-BasicID_0")


if __name__ == "__main__":
    unittest.main()
