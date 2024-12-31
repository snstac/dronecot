#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright Sensors & Signals LLC https://www.snstac.com/
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""DroneCOT Function Tests."""

import json
import os
import random
import unittest

import xml.etree.ElementTree as ET

import dronecot

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_random_test_data(file_path):
    json_obj = None
    topic = "test"

    with open(file_path, "r", encoding="utf-8") as file:
        _payload = file.readlines()
        payload = random.choice(_payload)

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

    return json_obj


def load_sample_data(file_path, line=0):
    json_obj = None
    topic = "test"

    with open(f"{THIS_DIR}/{file_path}", "r", encoding="utf-8") as file:
        _payload = file.readlines()
        payload = _payload[line]

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

    return json_obj


class FunctionsTestCase(unittest.TestCase):
    """
    Test class for functions... functions.
    """

    def setUp(self):
        self.test_data = load_random_test_data("data/WiFi.json")

    def test_wifi_nan_et(self):
        sample_data = load_sample_data("data/WiFi-NaN.json")

        sample_config = {
            "COT_STALE": "600",
            "COT_HOST_ID": "test_host",
            "COT_ACCESS": "test_access",
        }

        parsed_data = dronecot.functions.parse_sensor_data(sample_data)
        cot_xml = dronecot.functions.rid_uas_to_cot_xml(parsed_data, sample_config)
        # print(ET.tostring(cot_xml))

        self.assertIsNotNone(cot_xml)

        self.assertEqual(cot_xml.get("uid"), "RID.1787F04BM24010011195.uas")
        self.assertEqual(cot_xml.get("type"), "a-n-A-M-H-Q")
        self.assertEqual(cot_xml.get("access"), sample_config["COT_ACCESS"])
        self.assertEqual(cot_xml.get("how"), "m-g")

        point = cot_xml.find("point")
        self.assertIsNotNone(point)
        self.assertEqual(point.get("lat"), "37.759979")
        self.assertEqual(point.get("lon"), "-122.497734")
        self.assertEqual(point.get("ce"), "12")
        self.assertEqual(point.get("le"), "5")
        self.assertEqual(point.get("hae"), "28.0")

        detail = cot_xml.find("detail")
        self.assertIsNotNone(detail)

        cuas = detail.find("__cuas")
        self.assertIsNotNone(cuas)
        self.assertEqual(cuas.get("sensor_id"), "SNSTAC-CUAS-0002")
        self.assertEqual(cuas.get("rssi"), "-85")
        self.assertEqual(cuas.get("channel"), "6")
        self.assertEqual(cuas.get("timestamp"), "1735677508065")
        self.assertEqual(cuas.get("mac_address"), "7A:60:B8:80:BE:E4")
        self.assertEqual(cuas.get("type"), "WiFi NaN")

    def test_wifi_beacon_et(self):
        sample_data = load_sample_data("data/WiFi-beacon.json")

        sample_config = {
            "COT_STALE": "600",
            "COT_HOST_ID": "test_host",
            "COT_ACCESS": "test_access",
        }

        parsed_data = dronecot.functions.parse_sensor_data(sample_data)
        cot_xml = dronecot.functions.rid_uas_to_cot_xml(parsed_data, sample_config)
        # print(ET.tostring(cot_xml))

        self.assertIsNotNone(cot_xml)

        self.assertEqual(cot_xml.get("uid"), "RID.1787F04BM24010011195.uas")
        self.assertEqual(cot_xml.get("type"), "a-n-A-M-H-Q")
        self.assertEqual(cot_xml.get("access"), sample_config["COT_ACCESS"])
        self.assertEqual(cot_xml.get("how"), "m-g")

        point = cot_xml.find("point")
        self.assertIsNotNone(point)
        self.assertEqual(point.get("lat"), "37.759979")
        self.assertEqual(point.get("lon"), "-122.497734")
        self.assertEqual(point.get("ce"), "12")
        self.assertEqual(point.get("le"), "5")
        self.assertEqual(point.get("hae"), "28.0")

        detail = cot_xml.find("detail")
        self.assertIsNotNone(detail)

        cuas = detail.find("__cuas")
        self.assertIsNotNone(cuas)
        self.assertEqual(cuas.get("sensor_id"), "SNSTAC-CUAS-0002")
        self.assertEqual(cuas.get("rssi"), "-91")
        self.assertEqual(cuas.get("channel"), "6")
        self.assertEqual(cuas.get("timestamp"), "1735677509089")
        self.assertEqual(cuas.get("mac_address"), "7E:60:B8:80:BE:E4")
        self.assertEqual(cuas.get("type"), "WiFi beacon")

    def test_ble_legacy_et(self):
        sample_data = load_sample_data("data/BLE-legacy.json", 1)

        sample_config = {
            "COT_STALE": "600",
            "COT_HOST_ID": "test_host",
            "COT_ACCESS": "test_access",
        }

        parsed_data = dronecot.functions.parse_sensor_data(sample_data)
        cot_xml = dronecot.functions.rid_uas_to_cot_xml(parsed_data, sample_config)
        print(ET.tostring(cot_xml))

        self.assertIsNotNone(cot_xml)

        self.assertEqual(cot_xml.get("uid"), "RID.1787F04BM24010011195.uas")
        self.assertEqual(cot_xml.get("type"), "a-n-A-M-H-Q")
        self.assertEqual(cot_xml.get("access"), sample_config["COT_ACCESS"])
        self.assertEqual(cot_xml.get("how"), "m-g")

        point = cot_xml.find("point")
        self.assertIsNotNone(point)
        self.assertEqual(point.get("lat"), "37.759979")
        self.assertEqual(point.get("lon"), "-122.497734")
        self.assertEqual(point.get("ce"), "12")
        self.assertEqual(point.get("le"), "5")
        self.assertEqual(point.get("hae"), "28.0")

        detail = cot_xml.find("detail")
        self.assertIsNotNone(detail)

        cuas = detail.find("__cuas")
        self.assertIsNotNone(cuas)
        self.assertEqual(cuas.get("sensor_id"), "SNSTAC-CUAS-0002")
        self.assertEqual(cuas.get("rssi"), "-76")
        self.assertEqual(cuas.get("channel"), "0")
        self.assertEqual(cuas.get("timestamp"), "1735677508441")
        self.assertEqual(cuas.get("mac_address"), "DF:72:11:D2:6B:95")
        self.assertEqual(cuas.get("type"), "BLE legacy")

    def test_ble_long_range_et(self):
        sample_data = load_sample_data("data/BLE-long_range.json")

        sample_config = {
            "COT_STALE": "600",
            "COT_HOST_ID": "test_host",
            "COT_ACCESS": "test_access",
        }

        parsed_data = dronecot.functions.parse_sensor_data(sample_data)
        cot_xml = dronecot.functions.rid_uas_to_cot_xml(parsed_data, sample_config)
        print(ET.tostring(cot_xml))

        self.assertIsNotNone(cot_xml)

        self.assertEqual(cot_xml.get("uid"), "RID.1787F04BM24010011195.uas")
        self.assertEqual(cot_xml.get("type"), "a-n-A-M-H-Q")
        self.assertEqual(cot_xml.get("access"), sample_config["COT_ACCESS"])
        self.assertEqual(cot_xml.get("how"), "m-g")

        point = cot_xml.find("point")
        self.assertIsNotNone(point)
        self.assertEqual(point.get("lat"), "37.7599788")
        self.assertEqual(point.get("lon"), "-122.4977338")
        self.assertEqual(point.get("ce"), "12")
        self.assertEqual(point.get("le"), "5")
        self.assertEqual(point.get("hae"), "28.0")

        detail = cot_xml.find("detail")
        self.assertIsNotNone(detail)

        cuas = detail.find("__cuas")
        self.assertIsNotNone(cuas)
        self.assertEqual(cuas.get("sensor_id"), "SNSTAC-CUAS-0002")
        self.assertEqual(cuas.get("rssi"), "-71")
        self.assertEqual(cuas.get("channel"), "0")
        self.assertEqual(cuas.get("timestamp"), "1735677510381")
        self.assertEqual(cuas.get("mac_address"), "DF:72:11:D2:6B:95")
        self.assertEqual(cuas.get("type"), "BLE long range")


if __name__ == "__main__":
    unittest.main()
