"""Tests for Wi-Fi Open Drone ID frame parsing.

Regression for the Scapy beacon path: ``Dot11EltVendorSpecific.oui`` is an int,
so the old ``bytes(elt.oui)`` built a huge zero buffer and the ASTM vendor
element never matched — ``extract_odid_from_scapy_packet`` decoded nothing even
though ``extract_odid_from_dot11`` decoded the same frame.
"""

import struct

import pytest

from dronecot import wifi_parse


def _astm_beacon_frame(pack_body: bytes) -> bytes:
    """Build a raw 802.11 beacon carrying an ASTM ODID vendor IE."""
    fc = struct.pack("<H", 0x0080)  # mgmt, subtype 8 (beacon)
    dur = b"\x00\x00"
    dst = b"\xff\xff\xff\xff\xff\xff"
    src = b"\xaa\xbb\xcc\xdd\xee\xff"
    bssid = src
    seq = b"\x00\x00"
    fixed = b"\x00" * 8 + b"\x64\x00" + b"\x00\x00"  # timestamp + interval + caps
    # Vendor IE: OUI FA:0B:BC, type 0x0D, msg_counter 0x01, then the pack body.
    ie_payload = wifi_parse.ASTM_WIFI_OUI + bytes([0x0D, 0x01]) + pack_body
    ie = bytes([0xDD, len(ie_payload)]) + ie_payload
    return fc + dur + dst + src + bssid + seq + fixed + ie


def test_extract_odid_from_dot11_beacon():
    body = bytes(range(25))
    frame = _astm_beacon_frame(body)
    result = wifi_parse.extract_odid_from_dot11(frame)
    assert result is not None
    pack, meta = result
    assert pack == body
    assert meta.get("type") == "WiFi beacon"


def test_extract_odid_from_scapy_packet_matches_raw():
    """The Scapy path must decode the same beacon the byte parser does."""
    scapy_dot11 = pytest.importorskip("scapy.layers.dot11")
    body = bytes(range(25))
    frame = _astm_beacon_frame(body)
    pkt = scapy_dot11.Dot11(frame)

    raw = wifi_parse.extract_odid_from_dot11(frame)
    viascapy = wifi_parse.extract_odid_from_scapy_packet(pkt)

    assert raw is not None
    assert viascapy is not None, "scapy path failed on a frame the byte parser decoded"
    assert viascapy[0] == raw[0] == body
