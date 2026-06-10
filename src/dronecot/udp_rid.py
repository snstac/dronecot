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

"""Parse pre-decoded Wi-Fi / BLE Remote ID JSON into dronecot RIDWorker dicts.

Accepts the flat JSONL format broadcast over UDP by drone detection nodes
that decode ASTM F3411 Remote ID payloads locally before transmission:

  {"t": 1745000000.0, "mac": "fa:0b:bc:12:34:56", "radio": "wifi_beacon",
   "rssi": -68, "type": "Location/Vector", "lat": 40.7128, "lon": -74.0060,
   "alt": 120.5, "speed": 8.25, "hdg": 270.0, "id": null}

Only messages carrying position data (lat/lon) are converted; identity-only
frames (BasicID, OperatorID) without coordinates are silently dropped.
"""

import json
import logging
from typing import Optional

_logger = logging.getLogger(__name__)

# Maps "radio" field values to the sensor type labels used by rid_uas_to_cot_xml
_RADIO_TO_SENSOR_TYPE = {
    "wifi_beacon": "WiFi beacon",
    "wifi_nan": "WiFi NaN",
    "wifi_action": "WiFi NaN",
    "ble": "BLE",
    "ble_legacy": "BLE legacy",
    "ble_long_range": "BLE long range",
    "ble_coded": "BLE long range",
}


def parse_udp_rid_message(msg: dict, config=None) -> Optional[dict]:
    """Convert a pre-decoded Remote ID JSON message into a RIDWorker dict.

    Returns None for messages without valid position data.
    """
    cfg = config or {}

    lat = msg.get("lat")
    lon = msg.get("lon")
    if lat is None or lon is None:
        return None
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None

    radio = str(msg.get("radio", "")).lower()
    sensor_type = _RADIO_TO_SENSOR_TYPE.get(radio, radio or "Remote ID")

    uasid = msg.get("id") or msg.get("mac") or "Unknown"
    mac = str(msg.get("mac") or "")
    ts_ms = int(float(msg.get("t") or 0) * 1000)
    sensor_id = str(cfg.get("SENSOR_ID", cfg.get("sensor_id", "UDP-RID")))

    return {
        "Latitude": lat,
        "Longitude": lon,
        "AltitudeGeo": float(msg.get("alt") or 0.0),
        "SpeedHorizontal": float(msg.get("speed") or 0.0),
        "Direction": float(msg.get("hdg") or 0.0),
        "BasicID": uasid,
        "data": {
            "MAC address": mac,
            "RSSI": int(msg.get("rssi") or 0),
            "channel": int(msg.get("channel") or 0),
            "type": sensor_type,
            "timestamp": ts_ms,
            "sensor ID": sensor_id,
            "sensor_id": sensor_id,
        },
        "topic": "udp_rid",
    }


def parse_udp_rid_line(line: str, config=None) -> Optional[dict]:
    """Parse a single JSON line as received over UDP or read from a JSONL file."""
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, ValueError) as exc:
        _logger.debug("UDP RID JSON parse error: %s | line: %.80s", exc, line)
        return None
    return parse_udp_rid_message(msg, config)
