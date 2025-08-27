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


DEFAULT_MQTT_BROKER: str = "localhost"
DEFAULT_MQTT_PORT: int = 1883
DEFAULT_MQTT_TOPIC: str = "#"
DEFAULT_GPS_INFO_CMD: str = "gpspipe --json -n 5"

hostname = socket.gethostname()
DEFAULT_SENSOR_ID: str = f"dronecot_{hostname}"

DEFAULT_SENSOR_PAYLOAD_TYPE: str = "Unknown-Sensor-Payload-Type"

DEFAULT_SENSOR_COT_TYPE: str = "a-f-G-E-S-E"
DEFAULT_OP_COT_TYPE: str = "a-u-G"
DEFAULT_UAS_COT_TYPE: str = "a-u-A-M-H-Q"
DEFAULT_HOME_COT_TYPE: str = "a-u-G"
