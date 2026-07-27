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

"""Merge successive single Open Drone ID messages into one per-transmitter track.

Why this exists
---------------
A Remote ID transmitter using BLE legacy advertising can only fit **one** 25-byte
ODID message in an advertisement, so it rotates through message types:

    BasicID -> Location -> System -> OperatorID -> BasicID -> ...

Each message on its own is useless for tracking:

* BasicID carries the UAS serial but **no position**.
* Location carries a position but **no serial**.
* System carries the operator location but neither.

Without state, dronecot renders every advertisement independently, which means a
Location message becomes a CoT with the UID ``RID.Unknown-BasicID_0.uas`` — so
*every drone in range collapses onto a single track* — while BasicID and System
messages are dropped entirely because they have no position.

This module keeps a short-lived record per transmitter and merges messages into
it, so the CoT that goes out carries the serial from one advertisement and the
position from another. Wi-Fi and BLE transmitters that send a full ``0xF``
message pack already carry everything in one frame; they pass through unchanged.

Keying
------
Keyed on the advertiser MAC. ASTM F3411 requires the transmitting MAC to stay
constant for the duration of a flight session, which makes it the only field
guaranteed to be present on *every* message type. BasicID is the fallback for
sources that supply no MAC (serial/MQTT feeds).

Bounding
--------
Entries expire after ``ttl`` seconds of silence, and the table is hard-capped at
``max_tracks`` (oldest evicted first). An unbounded dict keyed on something an
outsider controls is a memory leak waiting to happen.
"""

import time

from typing import Any, Dict, Optional, Tuple

__all__ = [
    "ODIDAggregator",
    "DEFAULT_TRACK_TTL",
    "DEFAULT_MAX_TRACKS",
    "DEFAULT_ID_GRACE",
]

DEFAULT_TRACK_TTL = 120.0
DEFAULT_MAX_TRACKS = 512
# How long to wait for a BasicID before rendering a position-only track under a
# MAC-derived UID. Transmitters interleave BasicID with Location, so the serial
# is normally well under a second away.
DEFAULT_ID_GRACE = 5.0

# Bookkeeping emitted by odid.message_pack_to_dict that describes the *frame*
# rather than the aircraft. Always taken from the newest message rather than
# merged, so it never reports stale per-message context.
_FRAME_KEYS = ("_messages", "_msg_pack_size")

# Metadata sub-dict that carries sensor/receiver context (RSSI, channel, ...).
_META_KEY = "data"


def _is_empty(value: Any) -> bool:
    """True for values that must not overwrite an already-known good field.

    ``0`` and ``0.0`` are legitimate positions, speeds and headings, so only
    ``None`` and blank strings count as absent.
    """
    return value is None or (isinstance(value, str) and not value.strip())


def track_key(rid: dict) -> Optional[Tuple[str, str]]:
    """Return a ``(kind, value)`` aggregation key for a normalized RID dict.

    Returns ``None`` when the record identifies no transmitter at all, in which
    case it cannot be safely merged with anything and should pass through.
    """
    meta = rid.get(_META_KEY) or {}
    mac = meta.get("MAC address")
    if not _is_empty(mac):
        return ("mac", str(mac).strip().upper())

    basic_id = rid.get("BasicID", rid.get("BasicID_0"))
    if not _is_empty(basic_id):
        return ("rid", str(basic_id).strip())

    return None


def _has_id(rid: dict) -> bool:
    """True once the transmitter's own serial/ID is known."""
    return not _is_empty(rid.get("BasicID", rid.get("BasicID_0")))


def has_position(rid: dict) -> bool:
    """True if the record can render as either a UAS or an operator CoT."""
    uas = rid.get("Latitude") is not None and rid.get("Longitude") is not None
    op = (
        rid.get("OperatorLatitude") is not None
        and rid.get("OperatorLongitude") is not None
    )
    return uas or op


class ODIDAggregator:
    """Merge single ODID messages per transmitter, with TTL and size bounds."""

    def __init__(
        self,
        ttl: float = DEFAULT_TRACK_TTL,
        max_tracks: int = DEFAULT_MAX_TRACKS,
        id_grace: float = DEFAULT_ID_GRACE,
    ) -> None:
        self.ttl = float(ttl)
        self.max_tracks = int(max_tracks)
        self.id_grace = float(id_grace)
        # key -> (first_seen, last_seen, merged_record)  [monotonic clock]
        self._tracks: Dict[Tuple[str, str], Tuple[float, float, dict]] = {}

    def __len__(self) -> int:
        return len(self._tracks)

    def __bool__(self) -> bool:
        """An aggregator is always truthy, even with no tracks yet.

        Without this, ``__len__`` makes a freshly-constructed aggregator falsy,
        so the natural ``if aggregator:`` silently skips aggregation until the
        first track happens to be created -- which is exactly never, because
        tracks are only created *by* aggregating. Truthiness means "there is an
        aggregator", not "it is holding something".
        """
        return True

    def update(self, rid: dict) -> Optional[dict]:
        """Merge ``rid`` into its transmitter's track.

        Returns the merged record when it has enough to render a CoT, otherwise
        ``None`` (the message was absorbed and will contribute to a later one).

        Records that identify no transmitter pass straight through, so no source
        is ever silently swallowed by the aggregator.
        """
        if not rid:
            return None

        key = track_key(rid)
        if key is None:
            return rid if has_position(rid) else None

        now = time.monotonic()
        self.prune(now)

        previous = self._tracks.get(key)
        first_seen = previous[0] if previous else now
        merged = dict(previous[2]) if previous else {}
        self._merge_into(merged, rid)

        self._tracks[key] = (first_seen, now, merged)
        self._enforce_cap()

        if not has_position(merged):
            return None

        # Hold a position-only track briefly while waiting for the serial. A
        # transmitter interleaves BasicID with Location, so the serial is
        # usually a fraction of a second away -- rendering first would emit CoT
        # under a MAC-derived UID and then switch to the real serial, leaving
        # TWO markers in TAK for one aircraft. After the grace period, render
        # anyway: an unidentified drone still needs to be on the map.
        if self.id_grace > 0 and not _has_id(merged):
            if now - first_seen < self.id_grace:
                return None

        # Return a copy: the caller renders CoT from it and must not mutate the
        # track we keep for the next advertisement.
        return dict(merged)

    def _merge_into(self, merged: dict, rid: dict) -> None:
        """Overlay ``rid`` onto ``merged``, newest non-empty value winning."""
        for field, value in rid.items():
            if field == _META_KEY or field in _FRAME_KEYS:
                continue
            if _is_empty(value):
                continue
            merged[field] = value

        # Frame context always reflects the message that just arrived.
        for field in _FRAME_KEYS:
            if field in rid:
                merged[field] = rid[field]

        # Sensor metadata (RSSI, channel, timestamp) merges the same way, so a
        # message type that omits RSSI doesn't erase the last known value.
        incoming_meta = rid.get(_META_KEY) or {}
        if incoming_meta:
            meta = dict(merged.get(_META_KEY) or {})
            for field, value in incoming_meta.items():
                if not _is_empty(value):
                    meta[field] = value
            merged[_META_KEY] = meta

    def prune(self, now: Optional[float] = None) -> int:
        """Drop tracks unheard from for longer than ``ttl``. Returns count dropped."""
        now = time.monotonic() if now is None else now
        stale = [k for k, (_, seen, _rec) in self._tracks.items() if now - seen > self.ttl]
        for key in stale:
            del self._tracks[key]
        return len(stale)

    def _enforce_cap(self) -> None:
        """Evict the least recently heard tracks down to ``max_tracks``."""
        if self.max_tracks <= 0 or len(self._tracks) <= self.max_tracks:
            return
        ordered = sorted(self._tracks.items(), key=lambda kv: kv[1][1])
        for key, _ in ordered[: len(self._tracks) - self.max_tracks]:
            del self._tracks[key]
