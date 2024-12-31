#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 BlueMark Innovations BV
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

"""Open Drone ID Python module."""

import datetime
import struct

import pytz

from bitstruct import *


class ODIDValidBlocks:
    """Valid blocks for Open Drone ID messages."""

    BasicID0_valid = 0
    BasicID1_valid = 0
    LocationValid = 0
    SelfIDValid = 0
    SystemValid = 0
    OperatorIDValid = 0
    AuthValid = [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    # max 13 pages up to 255 bytes data


def decode_valid_blocks(payload, valid_blocks):
    valid_blocks.BasicID0_valid = payload[892]
    valid_blocks.BasicID1_valid = payload[893]
    valid_blocks.LocationValid = payload[894]
    valid_blocks.AuthValid[0] = payload[895]
    valid_blocks.AuthValid[1] = payload[896]
    valid_blocks.AuthValid[2] = payload[897]
    valid_blocks.AuthValid[3] = payload[898]
    valid_blocks.AuthValid[4] = payload[899]
    valid_blocks.AuthValid[5] = payload[900]
    valid_blocks.AuthValid[6] = payload[901]
    valid_blocks.AuthValid[7] = payload[902]
    valid_blocks.AuthValid[8] = payload[903]
    valid_blocks.AuthValid[9] = payload[904]
    valid_blocks.AuthValid[10] = payload[905]
    valid_blocks.AuthValid[11] = payload[906]
    valid_blocks.AuthValid[12] = payload[907]
    valid_blocks.AuthValid[13] = payload[908]
    # The current RemoteID standards allow up to 13 pages of Auth data.
    # valid_blocks.AuthValid[14] = payload[909]
    # valid_blocks.AuthValid[15] = payload[910]
    valid_blocks.SelfIDValid = payload[911]
    valid_blocks.SystemValid = payload[912]
    valid_blocks.OperatorIDValid = payload[913]
    return valid_blocks


def parse_payload(payload, valid_blocks) -> dict:
    """Parse Open Drone ID payload from validaded data."""
    pl: dict = {}
    if valid_blocks.BasicID0_valid == 1:
        pl = pl | parse_basicID0(payload)

    if valid_blocks.BasicID1_valid == 1:
        pl = pl | parse_basicID1(payload)

    if valid_blocks.LocationValid == 1:
        pl = pl | parse_Location(payload)

    if valid_blocks.SelfIDValid == 1:
        pl = pl | parse_SelfID(payload)

    if valid_blocks.SystemValid == 1:
        pl = pl | parse_System(payload)

    if valid_blocks.OperatorIDValid == 1:
        pl = pl | parse_OperatorID(payload)

    for x in range(16):
        if valid_blocks.AuthValid[x] == 1:
            pl = pl | parse_AuthPage(payload, x)

    print("Parsed payload")
    print(pl)
    return pl


def parse_basicID0(payload):
    pl = {}
    BasicID0_start_byte = 0
    [UAType] = struct.unpack(
        "I", payload[BasicID0_start_byte : BasicID0_start_byte + 4]
    )
    [IDType] = struct.unpack(
        "I", payload[BasicID0_start_byte + 4 : BasicID0_start_byte + 4 + 4]
    )
    pl["UAType"] = UAType
    pl["IDType"] = IDType
    if IDType == 1 or IDType == 2:
        pl["BasicID"] = (
            payload[BasicID0_start_byte + 8 : BasicID0_start_byte + 8 + 21]
            .decode("ascii")
            .rstrip("\x00")
        )
    else:
        pl["BasicID"] = (
            payload[BasicID0_start_byte + 8 : BasicID0_start_byte + 8 + 21].hex(),
        )
    return pl


def parse_basicID1(payload):
    pl = {}
    BasicID1_start_byte = 32
    [UAType] = struct.unpack(
        "I", payload[BasicID1_start_byte : BasicID1_start_byte + 4]
    )
    [IDType] = struct.unpack(
        "I", payload[BasicID1_start_byte + 4 : BasicID1_start_byte + 4 + 4]
    )
    pl["UAType"] = UAType
    pl["IDType"] = IDType
    if IDType == 1 or IDType == 2:
        pl["BasicID"] = (
            payload[BasicID1_start_byte + 8 : BasicID1_start_byte + 8 + 21]
            .decode("ascii")
            .rstrip("\x00")
        )
    else:
        pl["BasicID"] = payload[
            BasicID1_start_byte + 8 : BasicID1_start_byte + 8 + 21
        ].hex()
    print(pl)
    return pl


def parse_Location(payload):
    pl = {}
    Location_start_byte = 32 + 32

    [Status] = struct.unpack(
        "I", payload[Location_start_byte : Location_start_byte + 4]
    )
    pl["Status"] = Status

    [Direction] = struct.unpack(
        "f", payload[Location_start_byte + 4 : Location_start_byte + 4 + 4]
    )

    if Direction > 360 or Direction < 0:
        Direction = float("NaN")

    pl["Direction"] = Direction

    [SpeedHorizontal] = struct.unpack(
        "f", payload[Location_start_byte + 8 : Location_start_byte + 8 + 4]
    )
    if SpeedHorizontal > 254.25 or SpeedHorizontal < 0:
        SpeedHorizontal = float("NaN")
    [SpeedVertical] = struct.unpack(
        "f", payload[Location_start_byte + 12 : Location_start_byte + 12 + 4]
    )
    pl["SpeedHorizontal"] = SpeedHorizontal

    if SpeedVertical > 62 or SpeedVertical < -62:
        SpeedVertical = float("NaN")

    pl["SpeedVertical"] = SpeedVertical

    [Latitude] = struct.unpack(
        "d", payload[Location_start_byte + 16 : Location_start_byte + 16 + 8]
    )
    print("Latitude: ", Latitude)
    if Latitude == 0.0 or Latitude > 90.0 or Latitude < -90.0:
        Latitude = float("NaN")
    [Longitude] = struct.unpack(
        "d", payload[Location_start_byte + 24 : Location_start_byte + 24 + 8]
    )
    if Longitude == 0.0 or Longitude > 180.0 or Longitude < -180.0:
        Longitude = float("NaN")

    pl["Latitude"] = Latitude
    pl["Longitude"] = Longitude

    [AltitudeBaro] = struct.unpack(
        "f", payload[Location_start_byte + 32 : Location_start_byte + 32 + 4]
    )
    if AltitudeBaro <= -1000.0 or AltitudeBaro > 31767.5:
        AltitudeBaro = float("NaN")
    [AltitudeGeo] = struct.unpack(
        "f", payload[Location_start_byte + 36 : Location_start_byte + 36 + 4]
    )
    if AltitudeGeo <= -1000.0 or AltitudeGeo > 31767.5:
        AltitudeGeo = float("NaN")

    pl["AltitudeBaro"] = AltitudeBaro
    pl["AltitudeGeo"] = AltitudeGeo

    [HeightType] = struct.unpack(
        "I ", payload[Location_start_byte + 40 : Location_start_byte + 40 + 4]
    )
    [Height] = struct.unpack(
        "f", payload[Location_start_byte + 44 : Location_start_byte + 44 + 4]
    )
    if Height <= -1000.0 or Height > 31767.5:
        Height = float("NaN")

    pl["HeightType"] = HeightType
    pl["Height"] = Height

    [HorizAccuracy] = struct.unpack(
        "I", payload[Location_start_byte + 48 : Location_start_byte + 48 + 4]
    )
    [VertAccuracy] = struct.unpack(
        "I", payload[Location_start_byte + 52 : Location_start_byte + 52 + 4]
    )
    [BaroAccuracy] = struct.unpack(
        "I", payload[Location_start_byte + 56 : Location_start_byte + 56 + 4]
    )
    [SpeedAccuracy] = struct.unpack(
        "I", payload[Location_start_byte + 60 : Location_start_byte + 60 + 4]
    )
    [TSAccuracy] = struct.unpack(
        "I", payload[Location_start_byte + 64 : Location_start_byte + 64 + 4]
    )
    [TimeStamp] = struct.unpack(
        "f", payload[Location_start_byte + 68 : Location_start_byte + 68 + 4]
    )

    pl["HorizAccuracy"] = HorizAccuracy
    pl["VertAccuracy"] = VertAccuracy
    pl["BaroAccuracy"] = BaroAccuracy
    pl["SpeedAccuracy"] = SpeedAccuracy
    pl["TSAccuracy"] = TSAccuracy

    if TimeStamp != float("NaN") and TimeStamp > 0 and TimeStamp <= 60 * 60:
        pl["TimeStamp"] = (
            int(TimeStamp / 60),
            int(TimeStamp % 60),
            int(100 * (TimeStamp - int(TimeStamp))),
        )
    return pl


def parse_SelfID(payload):
    pl = {}
    SelfID_start_byte = 776
    [DescType] = struct.unpack("I", payload[SelfID_start_byte : SelfID_start_byte + 4])
    Desc = payload[SelfID_start_byte + 4 : SelfID_start_byte + 4 + 23]
    pl["DescType"] = DescType
    pl["Desc"] = Desc.decode("ascii").rstrip("\x00")
    return pl


def parse_System(payload):
    pl = {}
    System_start_byte = 808
    [OperatorLocationType] = struct.unpack(
        "I", payload[System_start_byte : System_start_byte + 4]
    )
    [ClassificationType] = struct.unpack(
        "I", payload[System_start_byte + 4 : System_start_byte + 4 + 4]
    )

    pl["OperatorLocationType"] = OperatorLocationType
    pl["ClassificationType"] = ClassificationType

    [OperatorLatitude] = struct.unpack(
        "d", payload[System_start_byte + 8 : System_start_byte + 8 + 8]
    )
    [OperatorLongitude] = struct.unpack(
        "d", payload[System_start_byte + 16 : System_start_byte + 16 + 8]
    )

    if OperatorLatitude == 0.0 or OperatorLatitude > 90.0 or OperatorLatitude < -90.0:
        OperatorLatitude = float("NaN")
    if (
        OperatorLongitude == 0.0
        or OperatorLongitude > 180.0
        or OperatorLongitude < -180.0
    ):
        OperatorLongitude = float("NaN")

    pl["OperatorLatitude"] = OperatorLatitude
    pl["OperatorLongitude"] = OperatorLongitude

    [AreaCount] = struct.unpack(
        "H", payload[System_start_byte + 24 : System_start_byte + 24 + 2]
    )
    [AreaRadius] = struct.unpack(
        "H", payload[System_start_byte + 26 : System_start_byte + 26 + 2]
    )
    [AreaCeiling] = struct.unpack(
        "f", payload[System_start_byte + 28 : System_start_byte + 28 + 4]
    )
    if AreaCeiling == -1000:
        AreaCeiling = float("NaN")
    [AreaFloor] = struct.unpack(
        "f", payload[System_start_byte + 32 : System_start_byte + 32 + 4]
    )
    if AreaFloor == -1000:
        AreaFloor = float("NaN")
    [CategoryEU] = struct.unpack(
        "I", payload[System_start_byte + 36 : System_start_byte + 36 + 4]
    )
    [ClassEU] = struct.unpack(
        "I", payload[System_start_byte + 40 : System_start_byte + 40 + 4]
    )
    [OperatorAltitudeGeo] = struct.unpack(
        "f", payload[System_start_byte + 44 : System_start_byte + 44 + 4]
    )
    if OperatorAltitudeGeo <= -1000.0 or OperatorAltitudeGeo > 31767.5:
        OperatorAltitudeGeo = float("NaN")
    [Timestamp] = struct.unpack(
        "I", payload[System_start_byte + 48 : System_start_byte + 48 + 4]
    )

    pl["AreaCount"] = AreaCount
    pl["AreaRadius"] = AreaRadius
    pl["AreaCeiling"] = AreaCeiling
    pl["AreaFloor"] = AreaFloor
    pl["CategoryEU"] = CategoryEU
    pl["ClassEU"] = ClassEU
    pl["OperatorAltitudeGeo"] = OperatorAltitudeGeo

    if Timestamp != float("NaN") and Timestamp != 0:
        pl["Timestamp"] = (
            datetime.datetime.fromtimestamp(
                (int(Timestamp) + 1546300800), pytz.UTC
            ).strftime("%Y-%m-%d %H:%M %Z"),
        )
    pl["TimestampRaw"] = Timestamp
    return pl


def parse_OperatorID(payload):
    pl = {}
    OperatorID_start_byte = 864

    [OperatorIdType] = struct.unpack(
        "I", payload[OperatorID_start_byte : OperatorID_start_byte + 4]
    )
    pl["OperatorIdType"] = OperatorIdType
    pl["OperatorID"] = (
        payload[OperatorID_start_byte + 4 : OperatorID_start_byte + 4 + 20]
        .decode("ascii")
        .rstrip("\x00")
    )
    return pl


def parse_AuthPage(payload, page):
    pl = {}
    AuthPage_start_byte = 136 + 40 * page

    [DataPage] = struct.unpack(
        "B", payload[AuthPage_start_byte + 0 : AuthPage_start_byte + 1]
    )
    [AuthType] = struct.unpack(
        "B", payload[AuthPage_start_byte + 4 : AuthPage_start_byte + 5]
    )
    pl["DataPage"] = DataPage
    pl["AuthType"] = AuthType

    if page == 0:
        global LastPageIndex
        global Length

        [LastPageIndex] = struct.unpack(
            "B", payload[AuthPage_start_byte + 8 : AuthPage_start_byte + 9]
        )
        [Length] = struct.unpack(
            "B", payload[AuthPage_start_byte + 9 : AuthPage_start_byte + 10]
        )
        [Timestamp] = struct.unpack(
            "I", payload[AuthPage_start_byte + 12 : AuthPage_start_byte + 12 + 4]
        )

        pl["LastPageIndex"] = LastPageIndex
        pl["Length"] = Length

        if Timestamp != float("NaN") and Timestamp != 0:
            pl["Timestamp"] = datetime.datetime.fromtimestamp(
                (int(Timestamp) + 1546300800), pytz.UTC
            ).strftime("%Y-%m-%d %H:%M %Z")

        AuthData = payload[AuthPage_start_byte + 16 : AuthPage_start_byte + 16 + 17]
        pl["AuthData"] = AuthData.hex()

    else:
        if page == LastPageIndex:
            # only print the chars within the specified length of the pages auth message
            AuthData = payload[
                AuthPage_start_byte + 16 : AuthPage_start_byte + 16 + (Length - 17) % 23
            ]
        else:
            AuthData = payload[AuthPage_start_byte + 16 : AuthPage_start_byte + 16 + 23]
            pl["AuthData"] = AuthData.hex()
    return pl
