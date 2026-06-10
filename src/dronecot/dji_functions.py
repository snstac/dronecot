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

"""DJI Drone ID Decoding Functions."""

import logging
import os
import struct

Logger = logging.getLogger(__name__)

DJI_PAYLOAD = {
    "serial_number": None,
    "device_type": None,
    "device_type_8": None,
    "op_lat": None,
    "op_lon": None,
    "uas_lat": None,
    "uas_lon": None,
    "height": None,
    "altitude": None,
    "home_lat": None,
    "home_lon": None,
    "freq": None,
    "speed_e": None,
    "speed_n": None,
    "speed_u": None,
    "rssi": None,
    "software": "DJICOT",
}


def parse_frame(frame):
    """
    Parse a DJI Drone ID frame and extract its components.

    Args:
        frame (bytes): The input frame to parse.

    Returns:
        tuple: (package_type (int), data (bytes))

    Frame structure:
        - Bytes 0-1: Frame header
        - Byte 2: Package type
        - Bytes 3-4: Package length (little-endian unsigned short)
        - Bytes 5+: Data payload

    Logs relevant fields for debugging.
    """
    frame_header = frame[:2]
    package_type = frame[2]
    length_bytes = frame[3:5]
    package_length = struct.unpack("H", length_bytes)[0]
    data = frame[5 : 5 + package_length - 5]

    Logger.debug(
        "Parsed frame - header=%s, type=%s, length=%s",
        frame_header, package_type, package_length
    )

    return package_type, data


def parse_data(data):
    """
    Parse the data payload of a DJI Drone ID frame.

    Args:
        data (bytes): The data payload to parse.
    Returns:
        dict: Parsed data fields.
    """
    payload = DJI_PAYLOAD.copy()
    try:
        payload = {
            "serial_number": data[:64].decode("utf-8").rstrip("\x00"),
            "device_type": data[64:128].decode("utf-8").rstrip("\x00"),
            "device_type_8": data[128],
            "op_lat": struct.unpack("d", data[129:137])[0],
            "op_lon": struct.unpack("d", data[137:145])[0],
            "uas_lat": struct.unpack("d", data[145:153])[0],
            "uas_lon": struct.unpack("d", data[153:161])[0],
            "height": struct.unpack("d", data[161:169])[0],
            "altitude": struct.unpack("d", data[169:177])[0],
            "home_lat": struct.unpack("d", data[177:185])[0],
            "home_lon": struct.unpack("d", data[185:193])[0],
            "freq": struct.unpack("d", data[193:201])[0],
            "speed_e": struct.unpack("d", data[201:209])[0],
            "speed_n": struct.unpack("d", data[209:217])[0],
            "speed_u": struct.unpack("d", data[217:225])[0],
            "rssi": struct.unpack("h", data[225:227])[0],
        }
    except UnicodeDecodeError as exc:
        if bool(os.getenv("DEBUG")):
            print(f"UnicodeDecodeError: {exc}")
        # If we fail to decode, it may indicate encrypted or partial data
        payload = {
            "device_type": "Unknown",
            "error": str(exc),
            "device_type_8": 255,
        }

    return payload
