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

"""Drone Open Remote ID to TAK Gateway."""

__version__ = "1.0.0"

# COMPAT Python 3.6 test/build work-around:
try:
    from .constants import (  # NOQA
        DEFAULT_MQTT_BROKER,
        DEFAULT_MQTT_PORT,
        DEFAULT_MQTT_TOPIC,
        DEFAULT_GPS_INFO_CMD,
        DEFAULT_SENSOR_COT_TYPE,
        DEFAULT_SENSOR_ID,
        DEFAULT_SENSOR_PAYLOAD_TYPE,
    )
    from .functions import (  # NOQA
        xml_to_cot,
        create_tasks,
    )
    from .classes import MQTTWorker, RIDWorker  # NOQA
    from .open_drone_id import (
        ODIDValidBlocks,
        decode_valid_blocks,
        parse_payload,
    )  # NOQA
except ImportError as exc:
    import warnings

    warnings.warn(f"COMPAT Python 3.6. Ignoring Exception {str(exc)}")
