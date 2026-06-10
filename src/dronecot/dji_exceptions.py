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

"""DJI Drone ID Exception Classes."""


class DJICOTError(Exception):
    """Base exception for all DJI Drone ID errors."""
    pass


class DJIDataError(DJICOTError):
    """Raised when DJI data is invalid or cannot be parsed."""
    pass


class DJIConnectionError(DJICOTError):
    """Raised when there are network connection issues with a DJI feed."""
    pass


class DJIConfigurationError(DJICOTError):
    """Raised when DJI feed configuration is invalid or missing."""
    pass
