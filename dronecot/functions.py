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
import json
import os
import xml.etree.ElementTree as ET

from configparser import SectionProxy
from typing import Optional, Set, Union

import pytak
import dronecot

__author__ = "Greg Albrecht <gba@snstac.com>"
__copyright__ = "Copyright Sensors & Signals LLC https://www.snstac.com"
__license__ = "Apache License, Version 2.0"


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

    op_id = data.get("OperatorID", "Unknown-OperatorID")
    uasid = data.get("BasicID_0", "Unknown-BasicID_0")

    cot_uid: str = f"RID.{op_id}"
    cot_type: str = "a-n-G"

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("_dronecot_")
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

    op_id = data.get("OperatorID", "Unknown-OperatorID")
    uasid = data.get("BasicID_0", "Unknown-BasicID_0")

    cot_uid: str = f"RID.{uasid}"
    cot_type: str = "a-n-A-M-F-Q"

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("_dronecot_")
    cotx.set("cot_host_id", cot_host_id)

    remarks_fields.append(f"OperatorID={op_id}")
    cotx.set("OperatorID", op_id)
    callsign = uasid

    contact: ET.Element = ET.Element("contact")
    contact.set("callsign", callsign)

    track: ET.Element = ET.Element("track")
    track.set("speed", str(data.get("SpeedHorizontal", 0)))

    link: ET.Element = ET.Element("link")
    link.set("uid", op_id)
    link.set("production_time", pytak.cot_time())
    link.set("type", "a-n-G")
    link.set("parent_callsign", op_id)
    link.set("relation", "p-p")

    detail = ET.Element("detail")
    detail.append(contact)
    detail.append(track)
    detail.append(cotx)
    detail.append(link)

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
    """Serialize sensor status data s Cursor on Target."""
    config = config or {}
    lat = config.get("SENSOR_LAT")
    lon = config.get("SENSOR_LON")
    alt = config.get("SENSOR_ALT", "9999999.0")

    if lat is None or lon is None:
        gps_info = get_gps_info(config)
        if gps_info:
            print(gps_info)
        else:
            return None

    if lat is None or lon is None:
        return None

    config = config or {}
    remarks_fields: list = []

    sensor_id = config.get("SENSOR_ID", "Unknown-SENSOR_ID")

    cot_uid: str = f"CUAS.{sensor_id}"
    cot_type: str = "a-f-G-E-S"

    cot_stale: int = int(config.get("COT_STALE", pytak.DEFAULT_COT_STALE))
    cot_host_id: str = config.get("COT_HOST_ID", pytak.DEFAULT_HOST_ID)

    cotx = ET.Element("_dronecot_")
    cotx.set("cot_host_id", cot_host_id)

    remarks_fields.append(f"C-UAS Sensor {sensor_id}")
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


def xml_to_cot(
    data: dict, config: Union[SectionProxy, dict, None] = None, func=None
) -> Optional[bytes]:
    """Return CoT XML object as an XML string."""
    cot: Optional[ET.Element] = getattr(dronecot.functions, func)(data, config)
    return (
        b"\n".join([pytak.DEFAULT_XML_DECLARATION, ET.tostring(cot)]) if cot else None
    )


def get_gps_info(config) -> Optional[dict]:
    """Get GPS Info data."""
    gpspipe_data: Optional[str] = None
    gps_data: Optional[str] = None
    gps_info_cmd = config.get("GPS_INFO_CMD", dronecot.DEFAULT_GPS_INFO_CMD)

    with os.popen(gps_info_cmd) as gps_info_cmd:
        gpspipe_data = gps_info_cmd.read()

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
