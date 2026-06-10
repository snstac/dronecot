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

"""Drone Open Remote ID to TAK Gateway (with DJI Drone ID and UDP Remote ID support)."""


from .constants import (  # NOQA
    DEFAULT_MQTT_TOPIC,
    DEFAULT_FEED_URL,
    DEFAULT_WIFI_INTERFACE,
    DEFAULT_WIFI_CHANNEL,
    DEFAULT_BLE_SERIAL,
    DEFAULT_BLE_BAUD_RATE,
    DEFAULT_SERIAL_BAUD_RATE,
    DEFAULT_SERIAL_TIMEOUT,
    DEFAULT_SERIAL_PORT,
    DEFAULT_GPS_INFO_CMD,
    DEFAULT_SENSOR_ID,
    DEFAULT_SENSOR_PAYLOAD_TYPE,
    DEFAULT_SENSOR_COT_TYPE,
    DEFAULT_OP_COT_TYPE,
    DEFAULT_HOME_COT_TYPE,
    DEFAULT_UAS_COT_TYPE,
    # UDP pre-decoded Remote ID constants
    DEFAULT_UDP_RID_PORT,
    DEFAULT_UDP_RID_HOST,
    # DJI Drone ID constants
    DEFAULT_DJI_FEED_URL,
    DEFAULT_DJI_TEXT_FEED_URL,
    DEFAULT_DJI_BINARY_PORT,
    DEFAULT_DJI_TEXT_PORT,
    DEFAULT_DJI_TCP_PORT,
    DEFAULT_DJI_BIND_ADDRESS,
    DEFAULT_DJI_COT_TYPE,
    DEFAULT_DJI_READ_BYTES,
    DEFAULT_DJI_SENSOR_LAT,
    DEFAULT_DJI_SENSOR_LON,
    DEFAULT_DJI_SENSOR_SN,
    DEFAULT_DJI_SENSOR_NAME,
    DEFAULT_DJI_SENSOR_TYPE,
    DEFAULT_DJI_SENSOR_COT_TYPE,
)

from .functions import (  # NOQA
    xml_to_cot,
    cot_to_xml,
    create_tasks,
    # DJI Drone ID functions
    gen_dji_cot,
    dji_uas_to_cot,
    dji_op_to_cot,
    dji_home_to_cot,
    dji_sensor_to_cot,
    dji_handle_frame,
    dji_handle_text_line,
    dji_handle_parsed_data,
)

from .udp_rid import (  # NOQA
    parse_udp_rid_message,
    parse_udp_rid_line,
)

from .classes import (  # NOQA
    BleWorker,
    MQTTWorker,
    RIDWorker,
    RXMockWorker,
    SerialWorker,
    WifiWorker,
    # UDP pre-decoded Remote ID worker
    UDPRIDWorker,
    # DJI Drone ID workers
    DJIWorker,
    DJINetWorker,
    DJITextWorker,
    DJIFileWorker,
    DJIListenerWorker,
    # Backward-compat aliases
    NetWorker,
    BinaryNetWorker,
    TextNetWorker,
    FileReplayWorker,
    TCPListenerWorker,
)

from .dji_exceptions import (  # NOQA
    DJICOTError,
    DJIDataError,
    DJIConnectionError,
    DJIConfigurationError,
)

from . import odid  # NOQA
from . import rid_normalize  # NOQA

from .open_drone_id import (
    ODIDValidBlocks,
    decode_valid_blocks,
    parse_payload,
)  # NOQA
