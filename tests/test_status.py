#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the runtime status surface RIDWorker writes for Cockpit.

These drive the coroutine with ``asyncio.run()`` rather than declaring bare
``async def`` tests. That is not a style choice: pytest-asyncio is not installed
in the build/CI environment for this package, and pytest SKIPS bare async tests
while still reporting the run as passed -- i.e. tests that cannot fail. Calling
asyncio.run() explicitly keeps them real regardless of plugins.
"""

import asyncio
import json
import logging
import os
import struct

import pytest

import pytak

from dronecot import classes, rid_normalize, rid_track


ODID_MESSAGE_SIZE = 25
PROTO_VERSION = 2

TEST_MAC = "AA:BB:CC:DD:EE:01"
TEST_SERIAL = "1596F3AD8E2B4C5D6E7F"

needs_statuswriter = pytest.mark.skipif(
    not hasattr(pytak, "StatusWriter"),
    reason="installed pytak has no StatusWriter (pre-7.4.0)",
)


def _basic_id_message(serial: str = TEST_SERIAL) -> bytes:
    """A single ODID BasicID message (type 0): serial, no position."""
    msg = bytearray(ODID_MESSAGE_SIZE)
    msg[0] = (0 << 4) | PROTO_VERSION
    msg[1] = (1 << 4) | 2
    msg[2:22] = serial.encode("ascii").ljust(20, b"\x00")
    return bytes(msg)


def _location_message(lat: float = 37.76, lon: float = -122.4) -> bytes:
    """A single ODID Location message (type 1): position, no serial."""
    msg = bytearray(ODID_MESSAGE_SIZE)
    msg[0] = (1 << 4) | PROTO_VERSION
    msg[1] = 0x20  # Status=2 (Airborne)
    msg[2] = 90
    msg[3] = 10
    msg[5:9] = struct.pack("i", int(lat * 1e7))
    msg[9:13] = struct.pack("i", int(lon * 1e7))
    msg[13:15] = struct.pack("H", 2000 + 200)
    msg[15:17] = struct.pack("H", 2000 + 200)
    msg[17:19] = struct.pack("H", 2000 + 100)
    return bytes(msg)


def _rid(msg: bytes, mac: str = TEST_MAC, rssi: int = -71) -> dict:
    """Normalize one ODID message the way a BLE capture worker would."""
    return rid_normalize.bytes_to_rid_dict(
        msg, {"MAC address": mac, "RSSI": rssi, "type": "BLE legacy (BlueZ)"}
    )


async def _noop_put(event):
    return None


@needs_statuswriter
class TestStatusSurface:
    """What the Cockpit plugin reads out of /run/dronecot/status.json.

    RIDWorker already made these decisions -- merge, render, drop -- they just
    went nowhere an operator could see. The risk with a status surface is that
    it reports the shape of the code rather than what actually happened, so
    these assert against real ODID advertisements pushed through the worker.
    """

    def _worker(self, tmp_path, ttl=120.0, id_grace=5.0):
        worker = classes.RIDWorker.__new__(classes.RIDWorker)
        worker.config = {}
        worker.net_queue = None
        worker.aggregator = rid_track.ODIDAggregator(ttl=ttl, id_grace=id_grace)
        worker._logger = logging.getLogger("test")
        worker.status = pytak.StatusWriter(
            "dronecot-test", path=str(tmp_path / "status.json")
        )
        worker.put_queue = _noop_put
        return worker

    def _handle(self, worker, data):
        asyncio.run(worker.handle_data(data))

    def _doc(self, worker):
        with open(worker.status.path) as handle:
            return json.load(handle)

    def test_id_only_fragment_is_counted_not_silently_dropped(self, tmp_path):
        """A BasicID advertisement carries no position, so it renders no CoT.

        On BLE legacy this is the majority of traffic. Before this surface it
        vanished at debug level, so a receiver hearing a drone loud and clear
        looked identical to one hearing nothing at all.
        """
        worker = self._worker(tmp_path)
        self._handle(worker, _rid(_basic_id_message()))

        doc = self._doc(worker)
        assert doc["counters"]["rx"] == 1
        assert doc["counters"]["merged_awaiting_position"] == 1
        assert "emitted" not in doc["counters"]
        # Nothing renderable yet, so nothing claims to be a contact.
        assert doc["recent"] == []
        assert doc["tracked"] == 1

    def test_merged_track_emits_and_appears_in_the_feed(self, tmp_path):
        """Serial from one advertisement, position from the next -> one contact."""
        worker = self._worker(tmp_path)
        self._handle(worker, _rid(_basic_id_message()))
        self._handle(worker, _rid(_location_message()))

        # Writes are rate-limited to 1/sec, so two messages in the same second
        # leave the file holding the first one's figures. That is by design --
        # a gateway taking hundreds of advertisements a second must not spend
        # its time serialising JSON -- and run()'s 5s heartbeat is what
        # reconciles it. Forcing here stands in for that heartbeat.
        worker.status.write(force=True)

        doc = self._doc(worker)
        assert doc["counters"]["rx"] == 2
        assert doc["counters"]["emitted"] >= 1
        entry = doc["recent"][-1]
        assert entry["uas"] == TEST_SERIAL
        assert entry["placed"] is True
        assert entry["rssi"] == -71
        assert entry["source"] == "BLE legacy (BlueZ)"
        assert entry["mac"] == TEST_MAC

    def test_two_transmitters_are_tracked_separately(self, tmp_path):
        """tracked is the aggregator's real size, not a message count."""
        worker = self._worker(tmp_path)
        self._handle(worker, _rid(_basic_id_message(), mac="AA:BB:CC:DD:EE:01"))
        self._handle(worker, _rid(_basic_id_message("OTHER"), mac="AA:BB:CC:DD:EE:02"))
        worker.status.write(force=True)

        assert self._doc(worker)["tracked"] == 2

    def test_empty_payload_is_not_counted_as_received(self, tmp_path):
        """A decoder that produced nothing is not a drone.

        Counting it would make a receiver hearing only noise indistinguishable
        from one hearing traffic, which is the exact confusion this file exists
        to remove.
        """
        worker = self._worker(tmp_path)
        self._handle(worker, {})
        assert not os.path.exists(worker.status.path)

    def test_unrenderable_record_is_counted_as_no_cot(self, tmp_path):
        """Aggregation off: a position-less record reaches the renderer and fails.

        With RID_TRACK_TTL=0 there is no aggregator, so the fragment goes
        straight to cot_to_xml, which cannot place it. That is a distinct
        outcome from "held for merging" and gets a distinct counter.
        """
        worker = self._worker(tmp_path)
        worker.aggregator = None
        self._handle(worker, _rid(_basic_id_message()))

        doc = self._doc(worker)
        assert doc["counters"]["rx"] == 1
        assert doc["counters"]["no_cot"] == 1
        assert "merged_awaiting_position" not in doc["counters"]
        # Still shown in the feed: it WAS decoded, it just could not be placed.
        assert doc["recent"][-1]["placed"] is False
        assert doc["recent"][-1]["uas"] == TEST_SERIAL


@needs_statuswriter
class TestStatusHeartbeat:
    """An idle-but-healthy gateway must keep writing."""

    def test_heartbeat_refreshes_the_file(self, tmp_path):
        worker = classes.RIDWorker.__new__(classes.RIDWorker)
        worker.config = {}
        worker.aggregator = rid_track.ODIDAggregator()
        worker._logger = logging.getLogger("test")
        worker.status = pytak.StatusWriter(
            "dronecot-test", path=str(tmp_path / "status.json")
        )

        async def _drive():
            task = asyncio.ensure_future(worker._heartbeat(interval=0.01))
            await asyncio.sleep(0.05)
            task.cancel()

        asyncio.run(_drive())

        with open(worker.status.path) as handle:
            doc = json.load(handle)
        # No traffic at all, yet the file exists and reports a wall clock the
        # UI can use to tell "quiet" from "stopped".
        assert doc["counters"] == {}
        assert doc["wall_t"] > 0
        assert doc["tracked"] == 0


@needs_statuswriter
class TestDJIStatusSurface:
    """AntSDR/DJI feeds use DJIWorker rather than RIDWorker."""

    def _worker(self, tmp_path):
        worker = classes.DJIWorker.__new__(classes.DJIWorker)
        worker.config = {"FEED_URL": "tcp://172.31.100.2:52002"}
        # handle_data does not consume net_queue. Keeping this synthetic worker
        # loop-free also works on Python 3.9 after an earlier asyncio.run()
        # closes and clears the process-wide default loop.
        worker.net_queue = None
        worker._logger = logging.getLogger("test")
        worker.status = pytak.StatusWriter(
            "dronecot-test", path=str(tmp_path / "status.json")
        )
        worker.put_queue = _noop_put
        return worker

    def _doc(self, worker):
        with open(worker.status.path) as handle:
            return json.load(handle)

    def test_text_frame_counts_received_and_emitted(self, tmp_path, monkeypatch):
        worker = self._worker(tmp_path)
        monkeypatch.setattr(
            classes.dronecot,
            "dji_handle_text_line",
            lambda data, config: [b"<event/>", b"<event/>"],
        )

        asyncio.run(worker.handle_data("dji_O,test"))

        doc = self._doc(worker)
        assert doc["counters"] == {"rx": 1, "emitted": 2}
        assert doc["recent"][-1] == {
            "t": doc["recent"][-1]["t"],
            "source": "dji-text",
            "placed": True,
            "events": 2,
        }

    def test_unrenderable_binary_frame_is_visible(self, tmp_path, monkeypatch):
        worker = self._worker(tmp_path)
        monkeypatch.setattr(
            classes.dronecot, "dji_handle_frame", lambda data, config: []
        )

        asyncio.run(worker.handle_data(b"binary-frame"))

        doc = self._doc(worker)
        assert doc["counters"] == {"rx": 1, "no_cot": 1}
        assert doc["recent"][-1]["source"] == "dji-binary"
        assert doc["recent"][-1]["placed"] is False

    def test_heartbeat_refreshes_a_quiet_dji_feed(self, tmp_path):
        worker = self._worker(tmp_path)

        async def _drive():
            task = asyncio.ensure_future(worker._heartbeat(interval=0.01))
            await asyncio.sleep(0.05)
            task.cancel()

        asyncio.run(_drive())

        assert self._doc(worker)["counters"] == {}


class TestStatusDegradesVisibly:
    """A pytak without StatusWriter must not take the gateway down.

    Fleet boxes run pytak 7.3.13, which has no StatusWriter at all.
    """

    def test_no_op_status_when_pytak_is_too_old(self, monkeypatch):
        monkeypatch.setattr(classes, "_StatusWriter", None)
        status = classes.make_status("dronecot", "0.1.0")

        # Every call RIDWorker makes must be safe on the stand-in.
        status.count("rx")
        status.count("emitted", 2)
        status.record(uas="X", placed=True)
        status.set(tracked=1)
        assert status.write() is False
        assert status.write(force=True) is False

    def test_worker_still_handles_data_with_no_statuswriter(self, monkeypatch):
        """The whole point: no StatusWriter must not break the data path.

        The renderer is stubbed so this test asserts what it claims to --
        that RIDWorker still aggregates and still enqueues -- rather than
        incidentally re-testing dronecot's CoT rendering against whatever
        pytak happens to be installed.
        """
        monkeypatch.setattr(classes, "_StatusWriter", None)
        monkeypatch.setattr(
            classes.dronecot, "cot_to_xml", lambda data, config, func: b"<event/>"
        )

        worker = classes.RIDWorker.__new__(classes.RIDWorker)
        worker.config = {}
        worker.aggregator = rid_track.ODIDAggregator()
        worker._logger = logging.getLogger("test")
        worker.status = classes.make_status("dronecot", "0.1.0")

        emitted = []

        async def _put(event):
            emitted.append(event)

        worker.put_queue = _put

        asyncio.run(worker.handle_data(_rid(_basic_id_message())))
        # Held for merging: no position yet, so nothing to send.
        assert emitted == []

        asyncio.run(worker.handle_data(_rid(_location_message())))

        assert isinstance(worker.status, classes._NoStatus)
        assert emitted, "CoT must still be produced when status is unavailable"

    def test_real_writer_used_when_available(self):
        if classes._StatusWriter is None:
            pytest.skip("installed pytak has no StatusWriter")
        assert not isinstance(classes.make_status("x", "0"), classes._NoStatus)

    def test_instance_status_uses_configured_app_and_path(self, monkeypatch, tmp_path):
        captured = {}

        def fake_writer(app_name, *, path=None, version=None):
            captured.update(app_name=app_name, path=path, version=version)
            return object()

        monkeypatch.setattr(classes, "_StatusWriter", fake_writer)
        path = str(tmp_path / "status.json")
        classes.make_worker_status(
            {"STATUS_APP": "dronecot-dronescout", "STATUS_PATH": path}
        )

        assert captured == {
            "app_name": "dronecot-dronescout",
            "path": path,
            "version": classes.dronecot.__version__,
        }
