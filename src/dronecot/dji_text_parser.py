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

"""AntSDR text CSV line parser for DJI Drone ID detections."""

import logging
from typing import Optional

from .dji_functions import DJI_PAYLOAD

Logger = logging.getLogger(__name__)


def _float_or_none(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _band_to_device_type_8(band: str) -> int:
    if band.isdigit():
        return int(band)
    if "/" in band:
        try:
            return int(band.split("/", maxsplit=1)[0])
        except ValueError:
            pass
    return 255


def dji_parse_text_line(line: str) -> Optional[dict]:
    """Parse an AntSDR ``dji_O,...`` text CSV line into a parse_data-style dict."""
    line = line.strip()
    if not line or not line.startswith("dji_O,"):
        return None

    if line.endswith(";"):
        line = line[:-1]

    parts = line.split(",")
    if len(parts) < 15:
        Logger.debug("Skipping short dji_O line: %s", line)
        return None

    speeds = parts[12].split("|")
    extra_parts = parts[13].split("|")

    serial = parts[5].strip()
    device_type = parts[4].strip()
    band = parts[1].strip()

    payload = DJI_PAYLOAD.copy()
    payload.update(
        {
            "serial_number": serial or None,
            "device_type": device_type or "Unknown",
            "device_type_8": _band_to_device_type_8(band),
            "op_lon": _float_or_none(parts[6]),
            "op_lat": _float_or_none(parts[7]),
            "uas_lon": _float_or_none(parts[8]),
            "uas_lat": _float_or_none(parts[9]),
            "home_lon": _float_or_none(parts[10]),
            "home_lat": _float_or_none(parts[11]),
            "freq": _float_or_none(parts[2]),
            "speed_e": _float_or_none(speeds[0]) if speeds else None,
            "speed_n": _float_or_none(speeds[1]) if len(speeds) > 1 else None,
            "speed_u": _float_or_none(extra_parts[2])
            if len(extra_parts) > 2
            else None,
            "height": _float_or_none(extra_parts[0]) if extra_parts else None,
            "altitude": _float_or_none(extra_parts[1])
            if len(extra_parts) > 1
            else None,
            "rssi": int(float(parts[3])) if parts[3] else None,
            "timestamp": parts[14].strip(),
            "band": band,
            "feed_format": "text",
        }
    )

    if band == "4" and not serial:
        payload["device_type_8"] = 4

    return payload
