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

"""DroneCOT Constants."""

import socket

DEFAULT_SERIAL_PORT: str = "/dev/ttyACM0"
DEFAULT_SERIAL_BAUD_RATE: int = 115200
DEFAULT_SERIAL_TIMEOUT: int = 10

DEFAULT_WIFI_INTERFACE: str = "wlan0"
DEFAULT_WIFI_CHANNEL: int = 6
DEFAULT_BLE_SERIAL: str = "auto"
DEFAULT_BLE_BAUD_RATE: int = 2000000

DEFAULT_FEED_URL: str = "serial://" + DEFAULT_SERIAL_PORT + ":" + str(DEFAULT_SERIAL_BAUD_RATE)

# DEFAULT_MQTT_BROKER: str = "localhost"
# DEFAULT_MQTT_PORT: int = 1883
DEFAULT_MQTT_TOPIC: str = "#"
DEFAULT_GPS_INFO_CMD: str = "gpspipe --json -n 5"

hostname = socket.gethostname()
DEFAULT_SENSOR_ID: str = f"dronecot_{hostname}"

DEFAULT_SENSOR_PAYLOAD_TYPE: str = "Unknown-Sensor-Payload-Type"

DEFAULT_SENSOR_COT_TYPE: str = "a-f-G-E-S-E"
DEFAULT_OP_COT_TYPE: str = "a-n-G"
DEFAULT_UAS_COT_TYPE: str = "a-n-A-M-H-Q"
DEFAULT_HOME_COT_TYPE: str = "a-n-G"

# DJI Drone ID (AntSDR) constants
DEFAULT_DJI_FEED_URL: str = "tcp://192.168.1.10:41030"
DEFAULT_DJI_TEXT_FEED_URL: str = "tcp://192.168.1.10:52002"
DEFAULT_DJI_BINARY_PORT: int = 41030
DEFAULT_DJI_TEXT_PORT: int = 52002
DEFAULT_DJI_TCP_PORT: int = 52002       # TCP listener port (server/scanner-push mode)
DEFAULT_DJI_BIND_ADDRESS: str = "0.0.0.0"
DEFAULT_DJI_COT_TYPE: str = "a-u-A-M-H-Q"
DEFAULT_DJI_READ_BYTES: int = 1024
DEFAULT_DJI_BREAD_CRUMBS_ENABLED: bool = True
DEFAULT_DJI_HIDE_INVALID_DATA: bool = False
DEFAULT_DJI_ALERT_ID: str = "drone-alert-unknown"
DEFAULT_DJI_MAX_HORIZONTAL_SPEED: float = 100.0
DEFAULT_DJI_SENSOR_LAT: float = 0.0
DEFAULT_DJI_SENSOR_LON: float = 0.0
DEFAULT_DJI_SENSOR_HAE: float = 9999999.0
DEFAULT_DJI_SENSOR_CE: float = 9999999.0
DEFAULT_DJI_SENSOR_LE: float = 9999999.0
DEFAULT_DJI_SENSOR_STALE: int = 600
DEFAULT_DJI_SENSOR_SN: str = "0001"
DEFAULT_DJI_SENSOR_NAME: str = "DJICOT"
DEFAULT_DJI_SENSOR_TYPE: str = "DJIDroneID"
DEFAULT_DJI_SENSOR_COT_TYPE: str = "a-f-G-E-S-E"
