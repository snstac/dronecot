#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for rid_normalize and wifi_parse."""

import base64
import json
import unittest

import dronecot
from dronecot import ble_parse, rid_normalize, wifi_parse


class TestRidNormalize(unittest.TestCase):
    def test_cuas_blob_from_fixture(self):
        path = "tests/data/WiFi-beacon.json"
        with open(path, encoding="utf-8") as handle:
            records = json.load(handle)
        data = records[0]["data"]
        blob = base64.b64decode(data["UASdata"])
        meta = {
            "MAC address": data["MAC address"],
            "RSSI": data["RSSI"],
            "channel": data["channel"],
            "type": data["type"],
        }
        pl = rid_normalize.cuas_blob_to_rid_dict(blob, meta)
        self.assertIsNotNone(pl)
        self.assertIn("BasicID", pl)
        self.assertEqual(pl["data"]["MAC address"], data["MAC address"])

    def test_pack_header(self):
        # Minimal pack: type packed, size 25, count 1, one basic id message placeholder
        pack = bytes([0xF0, 25, 1]) + bytes([0] * 25)
        pl = rid_normalize.pack_bytes_to_rid_dict(pack, {"MAC address": "AA:BB:CC:DD:EE:FF"})
        self.assertIsNotNone(pl)
        self.assertIn("data", pl)


class TestBleParse(unittest.TestCase):
    def test_service_data_pack(self):
        # AD: length, type 0x16, UUID FA FF, app 0x0D, counter, pack header
        pack = bytes([0xF0, 25, 1]) + bytes([0] * 25)
        service = bytes([0xFA, 0xFF, 0x0D, 0x00]) + pack
        ad = bytes([len(service) + 1, 0x16]) + service
        extracted = ble_parse.extract_odid_from_adv_data(ad)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted[0] >> 4, 0xF)


class TestWifiParse(unittest.TestCase):
    def test_beacon_vendor_ie(self):
        # OUI FA0BBC + type 0x0D + counter + fake pack
        ie = bytes([0xFA, 0x0B, 0xBC, 0x0D, 0x00, 0xF0, 25, 1]) + bytes([0] * 25)
        pack = wifi_parse.parse_beacon_vendor_ie(ie)
        self.assertIsNotNone(pack)
        self.assertEqual(pack[0] >> 4, 0xF)


if __name__ == "__main__":
    unittest.main()
