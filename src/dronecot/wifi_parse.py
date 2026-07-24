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

"""Extract Open Drone ID message packs from 802.11 Wi-Fi frames."""

import struct
from typing import Any, Dict, List, Optional, Tuple

# ASTM F3411 Wi-Fi Beacon vendor element
ASTM_WIFI_OUI = bytes([0xFA, 0x0B, 0xBC])
ASTM_WIFI_VEND_TYPE_BEACON = 0x0D

# Wi-Fi Alliance NAN service discovery
WIFI_ALLIANCE_OUI = bytes([0x50, 0x6F, 0x9A])
WIFI_ALLIANCE_VEND_TYPE_NAN = 0x13
ODID_NAN_SERVICE_ID = bytes([0x88, 0x69, 0x19, 0x9D, 0x92, 0x09])


def _format_mac(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02X}" for b in mac_bytes[:6])


def parse_beacon_vendor_ie(ie_data: bytes) -> Optional[bytes]:
    """Parse ASTM vendor IE (OUI FA:0B:BC, type 0x0D) → message pack bytes."""
    if len(ie_data) < 5:
        return None
    if ie_data[0:3] != ASTM_WIFI_OUI or ie_data[3] != ASTM_WIFI_VEND_TYPE_BEACON:
        return None
    # msg_counter at byte 4, pack follows
    return ie_data[5:]


def parse_nan_action_payload(payload: bytes) -> Optional[bytes]:
    """Parse NAN action frame body for ODID message pack (opendroneid-core-c wifi.c)."""
    if len(payload) < 8:
        return None

    offset = 0
    category = payload[offset]
    offset += 1
    action_code = payload[offset]
    offset += 1
    if category != 0x04 or action_code != 0x09:
        return None

    if len(payload) < offset + 4:
        return None
    oui = payload[offset : offset + 3]
    oui_type = payload[offset + 3]
    offset += 4
    if oui != WIFI_ALLIANCE_OUI or oui_type != WIFI_ALLIANCE_VEND_TYPE_NAN:
        return None

    while offset + 3 <= len(payload):
        attr_id = payload[offset]
        attr_len = struct.unpack_from("<H", payload, offset + 1)[0]
        offset += 3
        if offset + attr_len > len(payload):
            break

        attr_body = payload[offset : offset + attr_len]
        offset += attr_len

        if attr_id != 0x03 or len(attr_body) < 10:
            continue

        service_id = attr_body[0:6]
        instance_id = attr_body[6]
        requestor_instance_id = attr_body[7]
        service_control = attr_body[8]
        service_info_length = attr_body[9]

        if (
            service_id != ODID_NAN_SERVICE_ID
            or instance_id != 0x01
            or service_control != 0x00
        ):
            continue

        if len(attr_body) < 10 + service_info_length:
            continue

        service_info = attr_body[10 : 10 + service_info_length]
        if len(service_info) < 2:
            continue
        # message_counter + ODID_MessagePack_encoded
        return service_info[1:]

    return None


def iter_wifi_ies(frame_bytes: bytes, offset: int) -> List[Tuple[int, bytes]]:
    """Walk 802.11 information elements starting at offset."""
    elements = []
    pos = offset
    while pos + 2 <= len(frame_bytes):
        elem_id = frame_bytes[pos]
        elem_len = frame_bytes[pos + 1]
        pos += 2
        if pos + elem_len > len(frame_bytes):
            break
        elements.append((elem_id, frame_bytes[pos : pos + elem_len]))
        pos += elem_len
    return elements


def extract_odid_from_dot11(frame_bytes: bytes) -> Optional[Tuple[bytes, Dict[str, Any]]]:
    """
    Extract ODID pack bytes and metadata from a raw 802.11 frame.

    Returns (pack_bytes, meta) or None.
    """
    if len(frame_bytes) < 24:
        return None

    fc = struct.unpack_from("<H", frame_bytes, 0)[0]
    subtype = (fc >> 4) & 0xF
    type_bits = (fc >> 2) & 0x3
    if type_bits != 0:  # management only
        return None

    addr2 = frame_bytes[10:16]
    meta: Dict[str, Any] = {"MAC address": _format_mac(addr2)}

    mgmt_body_start = 24
    if subtype == 0x8:  # beacon
        # timestamp(8) + beacon_int(2) + capabilities(2) = 12
        ie_start = mgmt_body_start + 12
        for elem_id, elem_data in iter_wifi_ies(frame_bytes, ie_start):
            if elem_id == 0xDD:  # vendor specific
                pack = parse_beacon_vendor_ie(elem_data)
                if pack:
                    meta["type"] = "WiFi beacon"
                    return pack, meta
    elif subtype == 0xD:  # action
        pack = parse_nan_action_payload(frame_bytes[mgmt_body_start:])
        if pack:
            meta["type"] = "WiFi NaN"
            return pack, meta

    return None


def extract_odid_from_scapy_packet(packet) -> Optional[Tuple[bytes, Dict[str, Any]]]:
    """Extract ODID from a Scapy packet (Dot11 layer).

    Delegates to the byte-level ``extract_odid_from_dot11`` parser on the
    serialized Dot11 frame. This avoids a class of Scapy field-type bugs — e.g.
    ``Dot11EltVendorSpecific.oui`` is an int, so ``bytes(elt.oui)`` builds a huge
    zero buffer instead of the 3 OUI bytes and the ASTM vendor element never
    matches — and keeps Wi-Fi Beacon and NAN decoding on one proven code path.
    """
    try:
        from scapy.layers.dot11 import Dot11, RadioTap  # noqa
    except ImportError:
        return None

    if not packet.haslayer(Dot11):
        return None

    dot11 = packet.getlayer(Dot11)
    result = extract_odid_from_dot11(bytes(dot11))
    if not result:
        return None

    pack, meta = result
    # Enrich with Scapy-only signal info when present.
    if packet.haslayer(RadioTap):
        rssi = getattr(packet[RadioTap], "dBm_AntSignal", None)
        if rssi is not None:
            meta["RSSI"] = int(rssi)
    return pack, meta
