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

"""DroneCOT Functions."""

import asyncio
import base64
import json
import logging
import os
import subprocess
import xml.etree.ElementTree as ET

from configparser import SectionProxy
from typing import Optional, Set, Union
from urllib.parse import urlparse

import pytak
import dronecot
from datetime import datetime
import pytz

from .dji_functions import parse_frame, parse_data
from .dji_text_parser import dji_parse_text_line
from .udp_rid import parse_udp_rid_message, parse_udp_rid_line
from .constants import (
    DEFAULT_DJI_COT_TYPE,
    DEFAULT_DJI_SENSOR_LAT,
    DEFAULT_DJI_SENSOR_LON,
    DEFAULT_DJI_SENSOR_HAE,
    DEFAULT_DJI_SENSOR_CE,
    DEFAULT_DJI_SENSOR_LE,
    DEFAULT_DJI_SENSOR_STALE,
    DEFAULT_DJI_SENSOR_SN,
    DEFAULT_DJI_SENSOR_NAME,
    DEFAULT_DJI_SENSOR_TYPE,
    DEFAULT_DJI_SENSOR_COT_TYPE,
    DEFAULT_DJI_BREAD_CRUMBS_ENABLED,
    DEFAULT_DJI_HIDE_INVALID_DATA,
    DEFAULT_DJI_ALERT_ID,
    DEFAULT_DJI_MAX_HORIZONTAL_SPEED,
    DEFAULT_DJI_FEED_URL,
    DEFAULT_DJI_TEXT_PORT,
    DEFAULT_UDP_RID_PORT,
    DEFAULT_UDP_RID_HOST,
)

_DJI_Logger = logging.getLogger(__name__)

APP_NAME = "dronecot"


def _dji_feed_uses_text(config, feed_url: str, parsed) -> bool:
    """Return True if the configured DJI feed uses AntSDR text CSV format."""
    feed_format = str(config.get("FEED_FORMAT", "")).lower()
    if feed_format == "text":
        return True
    if parsed.port == DEFAULT_DJI_TEXT_PORT:
        return True
    return False


def create_tasks(config: SectionProxy, clitool: pytak.CLITool) -> Set[pytak.Worker,]:
    """Create specific coroutine task set for this application.

    Routes based on explicit config keys first, then FEED_URL scheme:
      DJI_TCP_PORT set -> DJIListenerWorker + DJIWorker (scanner-push listener)
      UDP_RID_PORT set -> UDPRIDWorker + RIDWorker (pre-decoded RID JSON)
      wireless://  -> WifiWorker + BleWorker + RIDWorker
      wifi://      -> WifiWorker + RIDWorker
      ble://       -> BleWorker + RIDWorker
      udp://       -> UDPRIDWorker + RIDWorker
      mqtt://      -> MQTTWorker + RIDWorker
      serial://    -> SerialWorker + RIDWorker  (default when no key/scheme set)
      tcp://       -> DJI*Worker + DJIWorker  (AntSDR connect-out)
      file://      -> DJIFileWorker + DJIWorker (offline replay)
    """
    tasks = set()
    net_queue: asyncio.Queue = asyncio.Queue()

    feed_url = str(config.get("FEED_URL", dronecot.DEFAULT_FEED_URL)).lower()
    parsed = urlparse(feed_url)

    if config.get("DJI_TCP_PORT"):
        tasks.add(dronecot.DJIListenerWorker(net_queue, config))
        tasks.add(dronecot.DJIWorker(clitool.tx_queue, config, net_queue))
    elif parsed.scheme == "udp" or config.get("UDP_RID_PORT"):
        tasks.add(dronecot.UDPRIDWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif "wireless" in feed_url:
        tasks.add(dronecot.WifiWorker(net_queue, config))
        tasks.add(dronecot.BleWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif "wifi" in feed_url:
        tasks.add(dronecot.WifiWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif "ble" in feed_url:
        tasks.add(dronecot.BleWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif parsed.scheme == "mqtt" or "mqtt" in feed_url:
        tasks.add(dronecot.MQTTWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif parsed.scheme == "serial" or "serial" in feed_url:
        tasks.add(dronecot.SerialWorker(net_queue, config))
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))
    elif parsed.scheme == "tcp":
        if _dji_feed_uses_text(config, feed_url, parsed):
            tasks.add(dronecot.DJITextWorker(net_queue, config))
        else:
            tasks.add(dronecot.DJINetWorker(net_queue, config))
        tasks.add(dronecot.DJIWorker(clitool.tx_queue, config, net_queue))
    elif parsed.scheme == "file":
        tasks.add(dronecot.DJIFileWorker(net_queue, config))
        tasks.add(dronecot.DJIWorker(clitool.tx_queue, config, net_queue))
    else:
        tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))

    if config.get("ENABLE_RX_MOCK", "0") == "1":
        tasks.add(dronecot.RXMockWorker(clitool.rx_queue, config))

    tasks.add(dronecot.SensorWorker(clitool.tx_queue, config))

    return tasks


def rid_op_to_cot_xml(  # NOQA pylint: disable=too-many-locals,too-many-branches,too-many-statements
    data: dict,
    config: Union[SectionProxy, dict, None] = None,
) -> Optional[ET.Element]:
    """
    Serialize Open Drone ID data as Cursor on Target.

    Parameters
    ----------
    craft : `dict`
        Key/Value data struct of decoded ADS-B aircraft data.
    config : `configparser.SectionProxy`
        Configuration options and values.
        Uses config options: UID_KEY, COT_STALE, COT_HOST_ID
    kown_craft : `dict`
        Optional list of know craft to transform CoT data.

    Returns
    -------
    `xml.etree.ElementTree.Element`
        Cursor-On-Target XML ElementTree object.
    """
    lat = data.get("OperatorLatitude")
    lon = data.get("OperatorLongitude")

    if lat is None or lon is None:
        return None

    config = config or {}
    remarks_fields: list = []

    uasid = data.get("BasicID", data.get("BasicID_0", "Unknown-BasicID_0"))
    op_id = data.get("OperatorID", f"Operator ({uasid[0:4]}...{uasid[-4:]})")

    # To match Drone Hone UID format:
    mac_address = data.get("MAC address")
    mac_address_text = str(mac_address or "")
    cot_uid = f"op-{mac_address or uasid}"

    cot_type: str = config.get("OP_COT_TYPE", dronecot.DEFAULT_OP_COT_TYPE)
    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("__cuas")
    cotx.set("cot_host_id", cot_host_id)

    remarks_fields.append(f"Remote ID: {uasid} Oper: {op_id} MAC: {mac_address}")
    cotx.set("OperatorID", op_id)
    cotx.set("UASID", op_id)
    cotx.set("MAC_address", mac_address_text)
    callsign = op_id

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    # <link uid="df:72:11:d2:6b:95" type="a-_-A-M-H-Q" parent_callsign="DroneBeacon_1195" relation="p-p" />
    # <creator uid="df:72:11:d2:6b:95" callsign="DroneBeacon_1195" type="a-_-A-M-H-Q" />
    link: ET.Element = ET.Element("link")
    link.set("uid", mac_address or uasid)
    link.set("type", "a-_-A-M-H-Q")
    link.set("parent_callsign", callsign)
    link.set("relation", "p-p")

    creator: ET.Element = ET.Element("creator")
    creator.set("uid", mac_address or uasid)
    creator.set("callsign", callsign)
    creator.set("type", "a-_-A-M-H-Q")

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(cotx)
    detail.append(link)
    detail.append(creator)

    remarks = ET.Element("remarks")
    remarks_fields.append(f"{cot_host_id}")
    _remarks = " ".join(list(filter(None, remarks_fields)))
    remarks.text = _remarks
    detail.append(remarks)

    cot_d = {
        "lat": str(lat),
        "lon": str(lon),
        "ce": str(data.get("HorizAccuracy", "9999999.0")),
        "le": str(data.get("VertAccuracy", "9999999.0")),
        "hae": str(data.get("OperatorAltitudeGeo", "9999999.0")),
        "uid": cot_uid,
        "cot_type": cot_type,
        "stale": cot_stale,
    }
    cot = pytak.gen_cot_xml(**cot_d)
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.findall("detail")[0]
    flowtags = _detail.findall("_flow-tags_")
    detail.extend(flowtags)
    cot.remove(_detail)
    cot.append(detail)

    return cot


def rid_uas_to_cot_xml(  # NOQA pylint: disable=too-many-locals,too-many-branches,too-many-statements
    data: dict,
    config: Union[SectionProxy, dict, None] = None,
) -> Optional[ET.Element]:
    """
    Serialize Open Drone ID data as Cursor on Target.

    Parameters
    ----------
    craft : `dict`
        Key/Value data struct of decoded ADS-B aircraft data.
    config : `configparser.SectionProxy`
        Configuration options and values.
        Uses config options: UID_KEY, COT_STALE, COT_HOST_ID
    kown_craft : `dict`
        Optional list of know craft to transform CoT data.

    Returns
    -------
    `xml.etree.ElementTree.Element`
        Cursor-On-Target XML ElementTree object.
    """
    lat = data.get("Latitude")
    lon = data.get("Longitude")

    if lat is None or lon is None:
        return None

    config = config or {}
    remarks_fields: list = []
    src_data = data.get("data", {})

    extra_json = src_data.get("extra")

    uasid = data.get("BasicID", data.get("BasicID_0", "Unknown-BasicID_0"))
    op_id = data.get("OperatorID", uasid)

    mac_address = src_data.get("MAC address")
    mac_address_text = str(mac_address or "")
    cot_uid = f"RID.{uasid}.uas"
    op_uid = f"op-{uasid}"

    cot_type: str = config.get("UAS_COT_TYPE", dronecot.DEFAULT_UAS_COT_TYPE)
    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    # Show last-seen time in Pacific Time Zone in remarks
    pacific = pytz.timezone('US/Pacific')
    pacific_time = datetime.now(pacific).strftime('%Y-%m-%d %H:%M:%S %Z')
    remarks_fields.append(f"Last Seen (Pacific): {pacific_time}")

    remarks_fields.append(f"Remote ID: {uasid}")
    remarks_fields.append(f"Oper: {op_id}")
    remarks_fields.append(f"MAC: {mac_address}")

    track: ET.Element = ET.Element("track")
    track.set("speed", str(data.get("SpeedHorizontal", 0)))
    track.set("course", str(data.get("Direction", 0)))

    height: ET.Element = ET.Element("height")
    height.set("value", str(data.get("AltitudeGeo", 0)))

    # link: ET.Element = ET.Element("link")
    # link.set("uid", op_uid)
    # link.set("production_time", pytak.cot_time())
    # link.set("type", "a-n-G")
    # link.set("parent_callsign", op_id)
    # link.set("relation", "p-p")

    sensor_id = str(
        src_data.get("sensor_id", src_data.get("sensor ID", dronecot.DEFAULT_SENSOR_ID))
    )
    sensor_type = str(src_data.get("type", dronecot.DEFAULT_SENSOR_PAYLOAD_TYPE))
    rssi = str(src_data.get("RSSI"))

    cuas: ET.Element = ET.Element("__cuas")
    cuas.set("sensor_id", sensor_id)
    cuas.set("rssi", rssi)
    cuas.set("channel", str(src_data.get("channel")))
    cuas.set("timestamp", str(src_data.get("timestamp")))
    cuas.set("mac_address", mac_address_text)
    cuas.set("type", sensor_type)
    cuas.set("host_id", cot_host_id)
    cuas.set("rid_op", op_id)
    cuas.set("rid_uas", uasid)

    if extra_json:
        cuas.set("sn_present", str(extra_json.get("SN present")))
        cuas.set("sn_valid", str(extra_json.get("SN valid")))
        cuas.set("manufacturer", str(extra_json.get("manufacturer")))
        cuas.set("model", str(extra_json.get("model")))
        cuas.set("type", str(extra_json.get("type")))
        cuas.set("application", str(extra_json.get("application")))
        cuas.set("weight", str(extra_json.get("weight")))
        cuas.set("dimensions", str(extra_json.get("dimensions")))
        remarks_fields.append(f"SN: {extra_json.get('serial number')}")
        remarks_fields.append(f"Manufacturer: {extra_json.get('manufacturer')}")
        remarks_fields.append(f"Model: {extra_json.get('model')}")
        remarks_fields.append(f"Type: {extra_json.get('type')}")
        remarks_fields.append(f"Application: {extra_json.get('application')}")
        remarks_fields.append(f"Weight (kg): {extra_json.get('weight')}")
        remarks_fields.append(f"Dimensions (mm): {extra_json.get('dimensions')}")

    if extra_json and extra_json.get("manufacturer") and extra_json.get("model"):
        callsign = f"{extra_json.get('manufacturer')} {extra_json.get('model')} ({uasid[-4:]})"
    else:
        callsign = f"{uasid[0:4]}...{uasid[-4:]}"

    remarks_fields.append(f"Sensor: {sensor_id}")

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    # <__dh-uas>
    #     <metadata uaType="HelicopterOrMultirotor" serialNumber="1787F04BM24010011195" description="" remoteId="DroneBeacon_1195" />
    #     <connectionData receivedBy="SNSTAC-Albrecht-Tab" rssi="-18" firstSeenTime="1767206636603" receiverSrc="Internal WiFi Scanner" lastUpdateTime="1767207011215" transmissionMethod="WiFiBeacon24Ghz" />
    #     <kinematicData operationalStatus="Undeclared" horizontalSpeed="255.0" verticalSpeed="158.25" />
    #     <operatorData />
    #     <supplementalData />
    # </__dh-uas>
    
    dh_uas: ET.Element = ET.Element("__dh-uas")

    metadata: ET.Element = ET.Element("metadata")
    metadata.set("uaType", str(data.get("UAType", "")))
    metadata.set("serialNumber", str(uasid))
    metadata.set("description", str(data.get("Desc", "")))
    metadata.set("remoteId", str(data.get("Remote ID", "")))
    dh_uas.append(metadata)

    connectionData: ET.Element = ET.Element("connectionData")
    connectionData.set("receivedBy", sensor_id)
    connectionData.set("rssi", rssi)
    connectionData.set("firstSeenTime", str(data.get("First Seen Time", "")))
    connectionData.set("receiverSrc", sensor_type)
    connectionData.set("lastUpdateTime", str(int(datetime.now().timestamp() * 1000)))
    connectionData.set("transmissionMethod", str(data.get("Transmission Method", "")))
    dh_uas.append(connectionData)

    kinematicData: ET.Element = ET.Element("kinematicData")
    kinematicData.set("operationalStatus", str(data.get("Operational Status", "Undeclared")))
    kinematicData.set("horizontalSpeed", str(data.get("SpeedHorizontal", "")))
    kinematicData.set("verticalSpeed", str(data.get("SpeedVertical", "")))
    dh_uas.append(kinematicData)

    operatorData: ET.Element = ET.Element("operatorData")
    dh_uas.append(operatorData)

    supplementalData: ET.Element = ET.Element("supplementalData")
    dh_uas.append(supplementalData)

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(track)
    # detail.append(link)
    detail.append(cuas)
    detail.append(height)
    detail.append(dh_uas)

    remarks = ET.Element("remarks")
    remarks_fields.append(f"{cot_host_id}")
    _remarks = " ".join(list(filter(None, remarks_fields)))
    remarks.text = _remarks
    detail.append(remarks)

    cot_d = {
        "lat": str(lat),
        "lon": str(lon),
        "ce": str(data.get("HorizAccuracy", "9999999.0")),
        "le": str(data.get("VertAccuracy", "9999999.0")),
        "hae": str(data.get("AltitudeGeo", "9999999.0")),
        "uid": cot_uid,
        "cot_type": cot_type,
        "stale": cot_stale,
    }
    cot = pytak.gen_cot_xml(**cot_d)
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.findall("detail")[0]
    flowtags = _detail.findall("_flow-tags_")
    detail.extend(flowtags)
    cot.remove(_detail)
    cot.append(detail)

    return cot


def sensor_status_to_cot(  # NOQA pylint: disable=too-many-locals,too-many-branches,too-many-statements
    data: dict,
    config: Union[SectionProxy, dict, None] = None,
) -> Optional[ET.Element]:
    """Serialize sensor status data as Cursor on Target."""
    config = config or {}
    lat = data.get("lat")
    lon = data.get("lon")
    hae = data.get("altHAE")
    status = data.get("status") or {}

    if lat is None or lon is None:
        gps_info = None
        try:
            gps_info = get_gps_info(data, config)
        except Exception as e:
            print(f"Unable to get GPS position: {e}")
        if not gps_info:
            return None
        if gps_info.get("lat") and gps_info.get("lon") and gps_info.get("altHAE"):
            lat = gps_info.get("lat")
            lon = gps_info.get("lon")
            hae = gps_info.get("altHAE")

    if lat is None or lon is None:
        return None

    config = config or {}
    remarks_fields: list = []

    sensor_id = data.get(
        "sensor_id", config.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID)
    )

    cot_uid: str = f"SNSTAC-CUAS.{sensor_id}"
    cot_type: str = config.get("SENSOR_COT_TYPE", dronecot.DEFAULT_SENSOR_COT_TYPE)

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("_dronecot_")
    cotx.set("cot_host_id", cot_host_id)

    remarks_fields.append(
        f"SNSTAC C-UAS Sensor {sensor_id} - {status.get('model')} "
        f"{status.get('status')} - Contact: info@snstac.com 415-598-8226"
    )
    cotx.set("sensor_id", sensor_id)
    callsign = sensor_id

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    track: ET.Element = ET.Element("track")
    track.set("speed", str(data.get("SpeedHorizontal", 0)))

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(track)
    detail.append(cotx)

    remarks = ET.Element("remarks")
    remarks_fields.append(f"{cot_host_id}")
    _remarks = " ".join(list(filter(None, remarks_fields)))
    remarks.text = _remarks
    detail.append(remarks)

    cot_d = {
        "lat": str(lat),
        "lon": str(lon),
        "ce": str(data.get("HorizAccuracy", "9999999.0")),
        "le": str(data.get("VertAccuracy", "9999999.0")),
        "hae": hae,
        "uid": cot_uid,
        "cot_type": cot_type,
        "stale": cot_stale,
    }
    cot = pytak.gen_cot_xml(**cot_d)
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.findall("detail")[0]
    flowtags = _detail.findall("_flow-tags_")
    detail.extend(flowtags)
    cot.remove(_detail)
    cot.append(detail)

    return cot


def xml_to_cot(
    data: dict, config: Union[SectionProxy, dict, None] = None, func=None
) -> Optional[bytes]:
    """Return a CoT XML object as an XML string, using the given func."""
    cot: Optional[ET.Element] = getattr(dronecot.functions, func)(data, config)
    return (
        b"\n".join([pytak.DEFAULT_XML_DECLARATION, ET.tostring(cot)]) if cot else None
    )


def cot_to_xml(
    data: dict, config: Union[SectionProxy, dict, None] = None, func=None
) -> Optional[bytes]:
    """Backward-compatible alias for xml_to_cot()."""
    return xml_to_cot(data, config, func)


def get_gps_info(data, config) -> Optional[dict]:
    """Get GPS Info data."""
    gpspipe_data: Optional[str] = None
    gps_data: Optional[str] = None
    # Lookup table for sensor_id to lat/lon/hae
    sensor_locations = {
        # Add sensor locations here, format: "sensor_id": {"lat": lat, "lon": lon, "altHAE": hae}
        # Example:
        # "SENSOR001": {"lat": 37.7749, "lon": -122.4194, "altHAE": "100.0"},
        "SNSTAC-CUAS-001": {"lat": 37.76, "lon": -122.4975, "altHAE": "54.0"},
        "SNSTAC-CUAS-002": {"lat": 37.8287637, "lon": -122.377797, "altHAE": "1.0"},
        "ds01240900000379": {"lat": 37.4048311, "lon": -121.9763388, "altHAE": "1.6"},
    }

    sensor_id = data.get("sensor_id", data.get("sensor ID", config.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID)))
    if sensor_id in sensor_locations:
        return sensor_locations[sensor_id]
    
    gps_info_cmd = config.get("GPS_INFO_CMD", dronecot.DEFAULT_GPS_INFO_CMD)
    try:
        gpspipe_data = subprocess.check_output(
            gps_info_cmd, shell=True, timeout=10
        ).decode()
    except subprocess.TimeoutExpired:
        print("Unable to get GPS fix, ignoring.")
        return None

    if not gpspipe_data:
        return None

    if "\n" in gpspipe_data:
        for data in gpspipe_data.split("\n"):
            if "TPV" in data:
                gps_data = data
                continue

    if not gps_data:
        return None

    gps_info = json.loads(gps_data)
    return gps_info


def parse_sensor_data(data):
    """Process decoded data from the sensor."""
    message = data
    protocol = message.get("protocol")
    if not protocol or str(protocol) != "1.0":
        return

    data = message.get("data")
    uasdata = data.get("UASdata")
    if not uasdata:
        return

    uasdata = base64.b64decode(uasdata)
    valid_blocks = dronecot.decode_valid_blocks(uasdata, dronecot.ODIDValidBlocks())

    pl = dronecot.parse_payload(uasdata, valid_blocks)

    # del data["UASdata"]
    pl["data"] = data
    pl["topic"] = message["topic"]

    return pl


# ---------------------------------------------------------------------------
# DJI Drone ID CoT generation functions
# ---------------------------------------------------------------------------

def _dji_is_valid_lat_lon(lat, lon) -> bool:
    """Return True if lat/lon are finite, non-zero, and in valid range."""
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return -90 <= lat_f <= 90 and -180 <= lon_f <= 180
    except (ValueError, TypeError):
        return False


def gen_dji_cot(  # NOQA pylint: disable=too-many-locals,too-many-branches,too-many-statements
    data, config: Union[SectionProxy, dict, None] = None, leg: str = "uas"
) -> Optional[ET.Element]:
    """Generate a Cursor on Target XML event from parsed DJI Drone ID data."""
    config = config or {}

    lat = data.get(f"{leg}_lat")
    lon = data.get(f"{leg}_lon")

    lat_lon_valid = _dji_is_valid_lat_lon(lat, lon)
    if not lat_lon_valid:
        lat = None
        lon = None

    if not lat_lon_valid and config.get("HIDE_INVALID_DATA", DEFAULT_DJI_HIDE_INVALID_DATA):
        return None

    freq = str(data.get("freq", 0.0))
    rssi = str(data.get("rssi", -999))
    serial_number = data.get("serial_number")
    uas_sn = serial_number or freq
    uas_type = data.get("device_type", "")

    cot_type: str = str(config.get("COT_TYPE", DEFAULT_DJI_COT_TYPE))
    cot_uid = f"DJI-{uas_sn}"
    if leg in ("op", "home"):
        cot_type = "a-u-G-U-C"
        cot_uid = f"DJI-{uas_sn}-{leg}"

    callsign = f"DJI {uas_type} {leg} ({uas_sn[-4:]})"
    ce = str(data.get("nac_p", "9999999.0"))

    if not lat_lon_valid:
        if leg in ("op", "home"):
            return None
        lat = config.get("SENSOR_LAT", DEFAULT_DJI_SENSOR_LAT)
        lon = config.get("SENSOR_LON", DEFAULT_DJI_SENSOR_LON)
        cot_type = "a-u-A-M-H-Q"
        callsign = f"{callsign} (Range)"
        ce = 1000.0 * abs(int(rssi))

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)
    sensor_id = str(config.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID))

    cuas = ET.Element("__cuas")
    cuas.set("sensor_id", sensor_id)
    cuas.set("sensor_sn", str(config.get("SENSOR_SN", DEFAULT_DJI_SENSOR_SN)))
    cuas.set("sensor_type", str(config.get("SENSOR_TYPE", DEFAULT_DJI_SENSOR_TYPE)))
    cuas.set("sensor_name", str(config.get("SENSOR_NAME", DEFAULT_DJI_SENSOR_NAME)))
    cuas.set("cot_host_id", cot_host_id)
    cuas.set("uas_type", uas_type)
    cuas.set("uas_type_8", str(data.get("device_type_8")))
    cuas.set("uas_sn", str(uas_sn))
    cuas.set("freq", freq)
    cuas.set("rssi", rssi)
    cuas.set("speed_e", str(data.get("speed_e", 0.0)))
    cuas.set("speed_n", str(data.get("speed_n", 0.0)))
    cuas.set("speed_u", str(data.get("speed_u", 0.0)))
    valid = "1" if lat_lon_valid else "0"
    cuas.set("valid_geo", valid)
    cuas.set("sn_present", valid)
    cuas.set("serial_valid", valid)

    crumbs = ET.Element("__bread_crumbs")
    crumbs.set("enabled", str(config.get("BREAD_CRUMBS_ENABLED", DEFAULT_DJI_BREAD_CRUMBS_ENABLED)))

    contact = ET.Element("contact")
    contact.set("callsign", callsign)

    track = ET.Element("track")
    track.set("course", data.get("course_point", "9999999.0"))
    track.set("speed", data.get("speed_point", "9999999.0"))

    remarks = ET.Element("remarks")
    remarks.text = (
        f"sn={uas_sn} ({uas_type}) freq={data.get('freq', 0.0)} "
        f"rssi={data.get('rssi', 0)} sensor_id={sensor_id}"
    )

    detail = ET.Element("detail")
    detail.append(remarks)
    detail.append(contact)
    detail.append(track)
    detail.append(cuas)
    detail.append(crumbs)

    cot_d = {
        "lat": str(lat),
        "lon": str(lon),
        "ce": ce,
        "le": str(data.get("nac_v", "9999999.0")),
        "hae": str(data.get("alt_geom", "9999999.0")),
        "uid": cot_uid,
        "cot_type": cot_type,
        "stale": cot_stale,
    }
    cot = pytak.gen_cot_xml(**cot_d)
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.find("detail")
    if _detail is not None:
        flowtags = _detail.findall("_flow-tags_")
        detail.extend(flowtags)
        cot.remove(_detail)
    cot.append(detail)

    return cot


def dji_sensor_to_cot(
    data, config: Union[SectionProxy, dict, None] = None
) -> Optional[ET.Element]:
    """Generate a CoT sensor beacon event for the DJI AntSDR sensor."""
    config = config or {}
    lat = config.get("SENSOR_LAT", DEFAULT_DJI_SENSOR_LAT)
    lon = config.get("SENSOR_LON", DEFAULT_DJI_SENSOR_LON)
    if lat is None or lon is None:
        return None

    sensor_id = config.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID)
    sensor_sn = config.get("SENSOR_SN", DEFAULT_DJI_SENSOR_SN)
    sensor_type = config.get("SENSOR_TYPE", DEFAULT_DJI_SENSOR_TYPE)
    cot_host_id = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)
    cot_uid = config.get("SENSOR_UID", f"CUAS-{sensor_type}-{sensor_sn}-{cot_host_id}")
    callsign = config.get("SENSOR_CALLSIGN", f"CUAS-{sensor_type}-{sensor_sn}")
    cot_type = config.get("SENSOR_COT_TYPE", DEFAULT_DJI_SENSOR_COT_TYPE)
    cot_stale = config.get("SENSOR_STALE", DEFAULT_DJI_SENSOR_STALE)

    cuas = ET.Element("__cuas")
    cuas.set("sensor_id", sensor_id)
    cuas.set("sensor_sn", sensor_sn)
    cuas.set("sensor_type", sensor_type)
    cuas.set("cot_host_id", cot_host_id)

    contact = ET.Element("contact")
    contact.set("callsign", callsign)

    remarks = ET.Element("remarks")
    remarks.text = f"sensor_id={sensor_id} sensor_sn={sensor_sn} sensor_type={sensor_type}: {data}"

    detail = ET.Element("detail")
    detail.append(remarks)
    detail.append(contact)
    detail.append(cuas)

    cot_d = {
        "lat": str(lat),
        "lon": str(lon),
        "ce": str(config.get("SENSOR_CE", DEFAULT_DJI_SENSOR_CE)),
        "le": str(config.get("SENSOR_LE", DEFAULT_DJI_SENSOR_LE)),
        "hae": str(config.get("SENSOR_HAE", DEFAULT_DJI_SENSOR_HAE)),
        "uid": cot_uid,
        "cot_type": cot_type,
        "stale": cot_stale,
    }
    cot = pytak.gen_cot_xml(**cot_d)
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.find("detail")
    if _detail is not None:
        flowtags = _detail.findall("_flow-tags_")
        detail.extend(flowtags)
        cot.remove(_detail)
    cot.append(detail)

    return cot


def dji_uas_to_cot(data, config: Union[SectionProxy, dict, None] = None) -> Optional[ET.Element]:
    """Generate CoT for DJI UAS (drone) position."""
    return gen_dji_cot(data, config, leg="uas")


def dji_op_to_cot(data, config: Union[SectionProxy, dict, None] = None) -> Optional[ET.Element]:
    """Generate CoT for DJI operator position."""
    return gen_dji_cot(data, config, leg="op")


def dji_home_to_cot(data, config: Union[SectionProxy, dict, None] = None) -> Optional[ET.Element]:
    """Generate CoT for DJI home position."""
    return gen_dji_cot(data, config, leg="home")


def dji_handle_parsed_data(
    parsed_data: dict, config: Union[SectionProxy, dict, None] = None
) -> list:
    """Generate CoT event bytes from a parsed DJI data dict."""
    config = config or {}
    events = []
    for func in ("dji_uas_to_cot", "dji_op_to_cot", "dji_home_to_cot"):
        event: Optional[bytes] = xml_to_cot(parsed_data, config, func)
        if event:
            events.append(event)
    return events


def dji_handle_text_line(
    line: str, config: Union[SectionProxy, dict, None] = None
) -> list:
    """Parse an AntSDR text CSV line and return CoT event bytes."""
    config = config or {}
    parsed_data = dji_parse_text_line(line)
    if not parsed_data:
        return []
    return dji_handle_parsed_data(parsed_data, config)


def dji_handle_frame(
    frame: bytearray, config: Union[SectionProxy, dict, None] = None
) -> list:
    """Parse a binary DJI Drone ID frame and return CoT event bytes."""
    config = config or {}
    try:
        package_type, data = parse_frame(frame)
    except Exception as exc:
        _DJI_Logger.warning("Error parsing DJI frame: %s", exc)
        return []
    if package_type != 0x01:
        _DJI_Logger.warning("Invalid DJI package type: %s", package_type)
        return []
    if not data:
        return []
    try:
        parsed_data = parse_data(data)
    except Exception as exc:
        _DJI_Logger.warning("Error parsing DJI data: %s", exc)
        return []
    return dji_handle_parsed_data(parsed_data, config)


def gen_sensor_cot(
    config: Union[SectionProxy, dict, None] = None,
    lat: float = 0.0,
    lon: float = 0.0,
    hae: float = 0.0,
    ce: str = "9999999.0",
    le: str = "9999999.0",
) -> Optional[ET.Element]:
    """Generate a periodic sensor beacon CoT event (a-f-G-E-S-E).

    Position sourced from caller: gpsd, static config, or null island.
    ce/le are '9999999.0' when accuracy is unknown.
    """
    config = config or {}
    sensor_id = config.get("SENSOR_ID", dronecot.DEFAULT_SENSOR_ID)
    cot_type = config.get("SENSOR_COT_TYPE", dronecot.DEFAULT_SENSOR_COT_TYPE)
    cot_stale = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    callsign = config.get("SENSOR_CALLSIGN", sensor_id)
    payload_type = config.get("SENSOR_PAYLOAD_TYPE", dronecot.DEFAULT_SENSOR_PAYLOAD_TYPE)

    contact = ET.Element("contact")
    contact.set("callsign", callsign)

    cuas = ET.Element("__cuas")
    cuas.set("sensor_id", sensor_id)
    cuas.set("type", payload_type)

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(cuas)

    cot = pytak.gen_cot_xml(
        lat=str(lat),
        lon=str(lon),
        hae=str(hae),
        ce=ce,
        le=le,
        uid=f"SENSOR.{sensor_id}",
        cot_type=cot_type,
        stale=cot_stale,
    )
    cot.set("how", "m-g")
    cot.set("access", config.get("COT_ACCESS", pytak.DEFAULT_COT_ACCESS))

    _detail = cot.find("detail")
    if _detail is not None:
        cot.remove(_detail)
    cot.append(detail)

    return cot
