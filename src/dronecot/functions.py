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
import subprocess
import xml.etree.ElementTree as ET

from configparser import SectionProxy
from typing import Optional, Set, Union

import pytak
import dronecot
from datetime import datetime
import pytz

APP_NAME = "dronecot"


def create_tasks(config: SectionProxy, clitool: pytak.CLITool) -> Set[pytak.Worker,]:
    """Create specific coroutine task set for this application.

    Parameters
    ----------
    config : `SectionProxy`
        Configuration options & values.
    clitool : `pytak.CLITool`
        A PyTAK Worker class instance.

    Returns
    -------
    `set`
        Set of PyTAK Worker classes for this application.
    """
    tasks = set()

    net_queue: asyncio.Queue = asyncio.Queue()

    feed_url = str(config.get("FEED_URL", dronecot.DEFAULT_FEED_URL)).lower()

    if "mqtt" in feed_url:
        tasks.add(dronecot.MQTTWorker(net_queue, config))
    elif "serial" in feed_url:
        tasks.add(dronecot.SerialWorker(net_queue, config))

    tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))

    # Optional compatibility shim for older PyTAK flows.
    # Newer PyTAK RXWorker signatures changed and can break this mock worker.
    if config.get("ENABLE_RX_MOCK", "0") == "1":
        tasks.add(dronecot.RXMockWorker(clitool.rx_queue, config))

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

    # To match Drone Hone UID format:
    mac_address = data.get("MAC address")
    mac_address_text = str(mac_address or "")
    cot_uid = f"{mac_address or uasid}"
    op_uid = f"op-{mac_address or uasid}"

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
