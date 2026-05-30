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

"""Parse BLE advertising data for Open Drone ID (ASTM F3411)."""

from typing import Dict, List, Optional, Tuple

# GAP Service Data 16-bit UUID, ASTM 0xFFFA, app code 0x0D
BLE_AD_TYPE_SERVICE_DATA = 0x16
ASTM_BLE_UUID = bytes([0xFA, 0xFF])
ASTM_BLE_APP_CODE = 0x0D

ODID_MESSAGE_SIZE = 25


def _format_mac(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02X}" for b in mac_bytes[:6])


def iter_ad_structures(adv_data: bytes) -> List[Tuple[int, bytes]]:
    """Walk BLE advertising data AD structures."""
    structures = []
    pos = 0
    while pos < len(adv_data):
        length = adv_data[pos]
        if length == 0:
            break
        pos += 1
        if pos + length > len(adv_data):
            break
        ad_type = adv_data[pos]
        ad_data = adv_data[pos + 1 : pos + length]
        structures.append((ad_type, ad_data))
        pos += length
    return structures


def parse_odid_service_data(ad_data: bytes) -> Optional[bytes]:
    """
    Parse ASTM BLE service data AD element.

    Layout: UUID (0xFA, 0xFF) + app_code (0x0D) + msg_counter + 25-byte message
    or message pack for extended payloads.
    """
    if len(ad_data) < 4:
        return None
    if ad_data[0:2] != ASTM_BLE_UUID or ad_data[2] != ASTM_BLE_APP_CODE:
        return None

    # msg_counter is ad_data[3]; ODID bytes follow
    payload = ad_data[4:]
    if not payload:
        return None

    if (payload[0] >> 4) == 0xF and len(payload) >= 3:
        return payload
    if len(payload) >= ODID_MESSAGE_SIZE:
        return payload[:ODID_MESSAGE_SIZE]
    return None


def extract_odid_from_adv_data(adv_data: bytes) -> Optional[bytes]:
    """Find ODID payload in BLE advertising bytes."""
    for ad_type, ad_data in iter_ad_structures(adv_data):
        if ad_type == BLE_AD_TYPE_SERVICE_DATA:
            pack = parse_odid_service_data(ad_data)
            if pack:
                return pack
    return None


def extract_odid_from_sniffle_adv(
    adv_data: bytes, mac: Optional[bytes] = None, rssi: Optional[int] = None
) -> Optional[Tuple[bytes, Dict]]:
    """Extract ODID from raw Sniffle advertising data bytes."""
    pack = extract_odid_from_adv_data(adv_data)
    if not pack:
        return None

    meta: Dict = {"type": "BLE"}
    if mac:
        meta["MAC address"] = _format_mac(mac)
    if rssi is not None:
        meta["RSSI"] = rssi
    return pack, meta
