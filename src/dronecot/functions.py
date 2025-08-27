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

    tasks.add(dronecot.MQTTWorker(net_queue, config))
    tasks.add(dronecot.RIDWorker(clitool.tx_queue, net_queue, config))

    return tasks


# {'AltitudeBaro': nan,
#  'AltitudeGeo': 212.0,
#  'AreaCeiling': nan,
#  'AreaCount': 1,
#  'AreaFloor': nan,
#  'AreaRadius': 500,
#  'BaroAccuracy': 4,
#  'CategoryEU': 1,
#  'ClassEU': 5,
#  'ClassificationType': 1,
#  'Desc': 'Recreational',
#  'DescType': 0,
#  'Direction': 126.0,
#  'Height': 115.5,
#  'HeightType': 0,
#  'HorizAccuracy': 10,
#  'Latitude': 37.7599566,
#  'Longitude': -122.4983164,
#  'OperatorAltitudeGeo': 96.0,
#  'OperatorID': 'WCzFzGDgIzxEnUcT',
#  'OperatorIdType': 0,
#  'OperatorLatitude': 37.7599983,
#  'OperatorLocationType': 0,
#  'OperatorLongitude': -122.4973975,
#  'SpeedAccuracy': 1,
#  'SpeedHorizontal': 12.75,
#  'SpeedVertical': nan,
#  'Status': 0,
#  'TSAccuracy': 15,
#  'Timestamp': ('2041-06-11 01:04 UTC',),
#  'TimestampRaw': 708224640,
#  'VertAccuracy': 4}


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
    op_id = data.get("OperatorID", uasid)

    cot_uid: str = f"RID.{uasid}.op"
    cot_type: str = config.get("OP_COT_TYPE", dronecot.DEFAULT_OP_COT_TYPE)

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("__cuas")
    cotx.set("cot_host_id", cot_host_id)

    remarks_fields.append(f"UAS ID={uasid} OperatorID={op_id}")
    cotx.set("OperatorID", op_id)
    cotx.set("UASID", op_id)
    callsign = op_id

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    detail = ET.Element("detail")
    detail.append(contact)
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

    extra_json = data.get("extra", {})
    if len(extra_json) > 0:
       if extra_json.get('SN present') == 1:
            print("extra")
            print("SN valid......",  extra_json.get('SN valid'))
            print("manufacturer......",  extra_json.get('manufacturer'))
            print("model......",  extra_json.get('model'))
            print("type......",  extra_json.get('type'))
            print("application......",  extra_json.get('application'))
            print("weight mtow [kg]......",  extra_json.get('weight'))
            print("dimensions [mm]......",  extra_json.get('dimensions'))
            print("")


    uasid = data.get("BasicID", data.get("BasicID_0", "Unknown-BasicID_0"))
    op_id = data.get("OperatorID", uasid)
    op_uid = f"RID.{op_id}.op"

    cot_uid: str = f"RID.{uasid}.uas"
    cot_type: str = config.get("UAS_COT_TYPE", dronecot.DEFAULT_UAS_COT_TYPE)

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    remarks_fields.append(f"UAS: {uasid}")
    remarks_fields.append(f"Operator: {op_id}")

    callsign = uasid

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    track: ET.Element = ET.Element("track")
    track.set("speed", str(data.get("SpeedHorizontal", 0)))

    link: ET.Element = ET.Element("link")
    link.set("uid", op_uid)
    link.set("production_time", pytak.cot_time())
    link.set("type", "a-n-G")
    link.set("parent_callsign", op_id)
    link.set("relation", "p-p")

    cuas: ET.Element = ET.Element("__cuas")
    sensor_id = src_data.get(
        "sensor_id", src_data.get("sensor_id", dronecot.DEFAULT_SENSOR_ID)
    )
    cuas.set("sensor_id", sensor_id)
    cuas.set("rssi", str(src_data.get("RSSI")))
    cuas.set("channel", str(src_data.get("channel")))
    cuas.set("timestamp", str(src_data.get("timestamp")))
    cuas.set("mac_address", str(src_data.get("MAC address")))
    cuas.set("type", str(src_data.get("type", dronecot.DEFAULT_SENSOR_PAYLOAD_TYPE)))
    cuas.set("host_id", cot_host_id)
    cuas.set("rid_op", op_id)
    cuas.set("rid_uas", uasid)

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(track)
    detail.append(link)
    detail.append(cuas)

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
            gps_info = get_gps_info(config)
        except Exception as e:
            print(f"Unable to get GPS fix: {e}")
        if not gps_info:
            return None

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


def get_gps_info(config) -> Optional[dict]:
    """Get GPS Info data."""
    gpspipe_data: Optional[str] = None
    gps_data: Optional[str] = None
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
