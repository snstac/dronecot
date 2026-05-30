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

"""Normalize Open Drone ID payloads into RIDWorker queue dicts."""

import time
from typing import Any, Dict, Optional, Union

from configparser import SectionProxy

import dronecot

ODID_MESSAGE_SIZE = 25
CUAS_BLOB_MIN_LEN = 900


def uas_meta_defaults(config: Union[SectionProxy, dict, None] = None) -> Dict[str, Any]:
    """Build default sensor metadata for wireless captures."""
    cfg = config or {}
    sensor_id = cfg.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID)
    return {
        "sensor_id": sensor_id,
        "sensor ID": sensor_id,
        "type": cfg.get("SENSOR_PAYLOAD_TYPE", dronecot.DEFAULT_SENSOR_PAYLOAD_TYPE),
        "timestamp": int(time.time() * 1000),
    }


def odid_parsed_to_rid_dict(parsed: dict) -> dict:
    """Map odid.message_pack_to_dict output to MQTT/RIDWorker field names."""
    out: Dict[str, Any] = {}
    if "UASID" in parsed:
        out["BasicID"] = parsed["UASID"]
    for key in (
        "IDType",
        "UAType",
        "Status",
        "Direction",
        "SpeedHorizontal",
        "SpeedVertical",
        "Latitude",
        "Longitude",
        "AltitudeBaro",
        "AltitudeGeo",
        "HeightType",
        "Height",
        "HorizAccuracy",
        "VertAccuracy",
        "BaroAccuracy",
        "SpeedAccuracy",
        "TSAccuracy",
        "TimestampLocation",
        "DescType",
        "Desc",
        "ClassificationType",
        "OperatorLocationType",
        "OperatorLatitude",
        "OperatorLongitude",
        "AreaCount",
        "AreaRadius",
        "AreaCeiling",
        "AreaFloor",
        "CategoryEU",
        "ClassEU",
        "OperatorAltitudeGeo",
        "TimestampRaw",
        "Timestamp",
        "OperatorIdType",
        "OperatorID",
    ):
        if key in parsed:
            out[key] = parsed[key]
    return out


def pack_bytes_to_rid_dict(pack: bytes, meta: Optional[dict] = None) -> Optional[dict]:
    """Decode an ASTM ODID message pack into a RIDWorker dict."""
    if not pack or len(pack) < 3:
        return None

    meta = dict(meta or {})
    msg_type = pack[0] >> 4

    if msg_type == 0xF:
        single_size = pack[1]
        pack_size = pack[2]
        if single_size != ODID_MESSAGE_SIZE:
            return None
        expected = 3 + single_size * pack_size
        if len(pack) < expected:
            return None
        messages = pack[3:expected]
        parsed = dronecot.odid.message_pack_to_dict(messages, pack_size)
        pl = odid_parsed_to_rid_dict(parsed)
    elif len(pack) >= ODID_MESSAGE_SIZE and msg_type <= 5:
        parsed = dronecot.odid.message_pack_to_dict(pack[:ODID_MESSAGE_SIZE], 1)
        pl = odid_parsed_to_rid_dict(parsed)
    else:
        return None

    data = uas_meta_defaults(meta)
    for key in ("MAC address", "RSSI", "channel", "type", "timestamp", "sensor ID", "sensor_id"):
        if key in meta:
            data[key] = meta[key]
    pl["data"] = data
    return pl


def cuas_blob_to_rid_dict(blob: bytes, meta: Optional[dict] = None) -> Optional[dict]:
    """Decode CUAS-style wrapped UASdata (MQTT sensor format) into RIDWorker dict."""
    if len(blob) < CUAS_BLOB_MIN_LEN:
        return None

    meta = dict(meta or {})
    valid_blocks = dronecot.decode_valid_blocks(blob, dronecot.ODIDValidBlocks())
    pl = dronecot.parse_payload(blob, valid_blocks)

    data = uas_meta_defaults(meta)
    for key in ("MAC address", "RSSI", "channel", "type", "timestamp", "sensor ID", "sensor_id"):
        if key in meta:
            data[key] = meta[key]
    pl["data"] = data
    return pl


def bytes_to_rid_dict(payload: bytes, meta: Optional[dict] = None) -> Optional[dict]:
    """Auto-detect ASTM message pack vs CUAS sensor wrapper."""
    if not payload:
        return None
    if len(payload) >= CUAS_BLOB_MIN_LEN and (payload[0] >> 4) != 0xF:
        pl = cuas_blob_to_rid_dict(payload, meta)
        if pl:
            return pl
    return pack_bytes_to_rid_dict(payload, meta)
