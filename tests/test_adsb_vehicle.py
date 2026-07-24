#!/usr/bin/env python3
# Copyright Sensors & Signals LLC https://www.snstac.com/
# SPDX-License-Identifier: Apache-2.0
"""Tests for SerialWorker MAVLink ADSB_VEHICLE -> RID dict (DroneScout Bridge)."""

import types
import unittest

from dronecot.classes import SerialWorker


def _adsb(**kw):
    return types.SimpleNamespace(**kw)


class AdsbVehicleTestCase(unittest.TestCase):
    def test_full_conversion(self):
        rid = SerialWorker._adsb_vehicle_to_rid_dict(
            _adsb(
                lat=407128000, lon=-740060000, altitude=120500,
                hor_velocity=825, ver_velocity=-50, heading=27000,
                callsign="DRONE1\x00\x00", ICAO_address=0x123456,
            )
        )
        self.assertAlmostEqual(rid["Latitude"], 40.7128, places=6)
        self.assertAlmostEqual(rid["Longitude"], -74.0060, places=6)
        self.assertEqual(rid["AltitudeGeo"], 120.5)          # mm -> m
        self.assertEqual(rid["SpeedHorizontal"], 8.25)       # cm/s -> m/s
        self.assertEqual(rid["Direction"], 270.0)            # cdeg -> deg
        self.assertEqual(rid["BasicID"], "DRONE1")

    def test_no_callsign_falls_back_to_icao(self):
        rid = SerialWorker._adsb_vehicle_to_rid_dict(
            _adsb(lat=407128000, lon=-740060000, callsign="", ICAO_address=0x123456)
        )
        self.assertEqual(rid["BasicID"], "ICAO-123456")

    def test_no_position_dropped(self):
        self.assertEqual(SerialWorker._adsb_vehicle_to_rid_dict(_adsb(lat=0, lon=0)), {})


if __name__ == "__main__":
    unittest.main()
