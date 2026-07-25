"""Tests for the enriched sensor / SIGINT detail in the RID CoT payload."""

import xml.etree.ElementTree as ET

from dronecot.functions import _rf_band, rid_uas_to_cot_xml


def test_rf_band():
    assert _rf_band(6) == "2.4 GHz"
    assert _rf_band("6") == "2.4 GHz"
    assert _rf_band(44) == "5 GHz"
    assert _rf_band(None) == ""
    assert _rf_band("nope") == ""


def _rid_data():
    return {
        "Latitude": 37.76,
        "Longitude": -122.49,
        "BasicID": "1787F04BM24010011195",
        "SpeedHorizontal": 0,
        "Direction": 0,
        "AltitudeGeo": 10.0,
        "data": {
            "MAC address": "AA:BB:CC:DD:EE:FF",
            "RSSI": -42,
            "channel": 6,
            "sensor_id": "wifi-rid",
        },
    }


def test_rid_cot_carries_sensor_detail():
    config = {
        "SENSOR_MODEL": "Atheros AR9271",
        "SENSOR_TYPE": "Wi-Fi Open Drone ID",
    }
    event = rid_uas_to_cot_xml(_rid_data(), config)
    assert event is not None
    xml = ET.tostring(event, encoding="unicode")

    cuas = event.find(".//__cuas")
    assert cuas is not None
    assert cuas.get("sensor_model") == "Atheros AR9271"
    assert cuas.get("sensor_method") == "Wi-Fi Open Drone ID"
    assert cuas.get("band") == "2.4 GHz"
    assert cuas.get("rssi") == "-42"
    assert cuas.get("channel") == "6"

    remarks = event.find(".//remarks")
    assert remarks is not None and remarks.text
    assert "RSSI: -42 dBm" in remarks.text
    assert "2.4 GHz" in remarks.text
    assert "Atheros AR9271" in remarks.text
