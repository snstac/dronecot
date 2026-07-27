## DroneCOT 2.3.0

Correctness release for single-message Remote ID. A BLE legacy transmitter fits
only ONE 25-byte ODID message per advertisement and rotates through message
types, so the serial, the UAS position and the operator location arrive in
*different* frames. DroneCOT rendered each frame independently, which broke
badly in the field.

- **Fix: CoT XML could contain NUL bytes and fail to parse.** ODID pads its
  fixed-width ASCII fields (20-byte serial, 23-byte text) with NUL, and
  `clean_SN()` / `clean_string()` stripped only whitespace. Any UAS whose serial
  was shorter than the field emitted a CoT UID such as
  `RID.SHORTSN\0\0\0....uas` — 82 NUL bytes in the document, which is illegal in
  XML 1.0 and will not reparse. Both cleaners now strip NUL and all C0 control
  characters. Affected every source (Wi-Fi, BLE, serial, MQTT); went unnoticed
  because every committed fixture uses a full-width 20-character serial.
- **Fix: every drone collapsed onto one track.** A Location message carries a
  position but no serial, so it rendered with the constant UID
  `RID.Unknown-BasicID_0.uas` — all aircraft in range shared one track. The UID
  now falls back to the advertiser MAC (`MAC-<addr>`) so distinct transmitters
  stay distinct.
- **Fix: BasicID and System messages were silently dropped**, having no position
  of their own.
- **New `rid_track.ODIDAggregator`**: merges successive single ODID messages per
  transmitter (keyed on the advertiser MAC, which ASTM F3411 requires to be
  stable for a flight session) so a CoT carries the serial from one
  advertisement and the position from another. TTL-expired and hard-capped to
  bound memory. Wired into `RIDWorker.handle_data()`, the single choke point all
  workers feed, so Wi-Fi, BLE, serial, MQTT and UDP all benefit. Full `0xF`
  message packs are unaffected — they already carry everything in one frame.
  Tunable via `RID_TRACK_TTL` (default 120 s; set 0 to disable),
  `RID_TRACK_MAX` (default 512) and `RID_TRACK_ID_GRACE` (default 5 s).
  `RID_TRACK_ID_GRACE` briefly holds a position-only track while waiting for
  its serial, so one aircraft does not appear as two TAK markers (first under a
  MAC-derived UID, then under the real serial); after the grace period an
  unidentified drone renders anyway.

  **Measured against a live BlueMark DroneBeacon DB120** over 234 real BLE
  advertisements: without aggregation only 57 (24%) rendered as CoT and the
  real serial NEVER appeared — every event used the MAC fallback UID. With
  aggregation 230 (98%) rendered, all under the correct serial
  `RID.1787F04BM24010011195.uas`. The transmitter sent BasicID, Location and
  System as separate advertisements and no `0xF` message packs at all,
  confirming the single-message rotation this release exists to handle.
- **Fix: operator CoT UID ignored the MAC.** `rid_op_to_cot_xml()` read
  `data["MAC address"]`, but wireless captures put it in `data["data"]`, so the
  Drone-Hone-style `op-<mac>` UID never actually used a MAC.
- Replace deprecated `datetime.utcfromtimestamp()` (Python 3.12+ warning).
- Tests: 16 new, including a real ASTM F3411 advertisement captured off the air
  from a BlueMark DroneBeacon DB120 — the existing fixtures are all message
  packs or CUAS blobs and never exercised the single-message path.

## DroneCOT 2.2.5

- Enrich RID CoT `<__cuas>` detail and remarks with `sensor_model`,
  `sensor_method` and `band`. New `SENSOR_MODEL` / `SENSOR_TYPE` config.

## DroneCOT 2.2.4

- `wifi_parse`: fix `extract_odid_from_scapy_packet()`, which decoded zero
  beacons because `bytes(elt.oui)` on an int produced a 16 MB zero buffer. Now
  delegates to `extract_odid_from_dot11(bytes(dot11))`.

## DroneCOT 2.2.3

- SerialWorker: handle MAVLink **ADSB_VEHICLE** messages (in addition to
  OPEN_DRONE_ID_MESSAGE_PACK), so Remote ID receivers that emit ADS-B-style
  frames — e.g. the **BlueMark DroneScout Bridge (DS101)** in ADS-B output mode
  — are decoded to CoT. Adds a test for the ADSB_VEHICLE -> RID conversion.

## DroneCOT 2.2.2

- Fix UTC timestamp handling on Python 3.9 and 3.10.

## DroneCOT 2.2.1

- Use PyTAK shared CoT event, point, detail, remarks, and serialization helpers.
- Replace `pytz` timestamp handling with standard-library timezone handling.
- Require `pytak >= 7.3.12`.

## DroneCOT 2.2.0

- Add `SensorWorker`: periodic `a-f-G-E-S-E` sensor CoT heartbeat, emitted every `SENSOR_KEEPALIVE_PERIOD` seconds (default 30).
- Position sourced from system gpsd if present (mode 2/3 fix); falls back to static `SENSOR_LAT`/`SENSOR_LON`/`SENSOR_HAE` config; falls back to null island (0, 0, 0).
- Add `gen_sensor_cot()`: reusable CoT generator for sensor beacon events, used by `SensorWorker`.
- New constants: `DEFAULT_SENSOR_KEEPALIVE_PERIOD = 30`, `DEFAULT_SENSOR_LAT/LON/HAE = 0.0`.
- Add `gpsd-py3` as optional runtime dependency (soft import, gracefully absent).

## DroneCOT 2.1.5

- Add `takproto` to postinst pip install; enables TAK Protocol v1 protobuf encoding over WebSocket when connected to TAK Server via `wss://`.

## DroneCOT 2.1.4

- Fix packaging: `postinst` now installs `aiomqtt` and `pymavlink` via pip for Debian systems where these packages are not yet available in the distro repos.

## DroneCOT 2.1.3

- Fix: make `aiomqtt` a conditional import so the package loads without it when MQTT is not used; `MQTTWorker` raises `ImportError` with a helpful message if aiomqtt is missing at runtime.

## DroneCOT 2.1.2

- Fix: `DJI_TCP_PORT` and `UDP_RID_PORT` config keys now take precedence over `FEED_URL` in `create_tasks` routing, eliminating the need to set `FEED_URL=` when using the DJI listener or UDP Remote ID worker without an explicit feed URL.

## DroneCOT 2.1.1

- Fix: `DJIWorker` argument order in `create_tasks` (`net_queue` and `config` were swapped in all three call sites).

## DroneCOT 2.1.0

- Add `UDPRIDWorker`: UDP listener (default port 9999) for pre-decoded Wi-Fi / BLE Remote ID JSON broadcasts from drone detection nodes.
- Add `udp_rid.py` module: `parse_udp_rid_message()` and `parse_udp_rid_line()` convert flat decoded JSONL (`t`, `mac`, `radio`, `rssi`, `lat`, `lon`, `alt`, `speed`, `hdg`, `id`) to RIDWorker-compatible dicts.
- Map `radio` field values (`wifi_beacon`, `wifi_nan`, `ble_legacy`, `ble_long_range`, `ble_coded`) to sensor type labels used by CoT generator.
- `create_tasks` now routes `udp://` feed URL or `UDP_RID_PORT` config option to `UDPRIDWorker` + `RIDWorker`.
- Fix: `wifi://`, `ble://`, `wireless://` branches now correctly include `RIDWorker` to consume the net_queue they produce.
- New constants: `DEFAULT_UDP_RID_PORT = 9999`, `DEFAULT_UDP_RID_HOST = "0.0.0.0"`.

## DroneCOT 2.0.0

- Absorbed DJI Drone ID (DJICOT) support directly into dronecot package.
- Added `DJIWorker`, `DJINetWorker`, `DJITextWorker`, `DJIFileWorker`, `DJIListenerWorker` for AntSDR binary and text CSV feeds.
- Added `gen_dji_cot`, `dji_uas_to_cot`, `dji_op_to_cot`, `dji_home_to_cot`, `dji_sensor_to_cot` CoT generators.
- Added `dji_handle_frame`, `dji_handle_text_line`, `dji_handle_parsed_data` feed handlers.
- Added `dji_functions.py` (binary frame parser) and `dji_text_parser.py` (AntSDR CSV parser).
- Added `dji_exceptions.py`: `DJICOTError`, `DJIDataError`, `DJIConnectionError`, `DJIConfigurationError`.
- `create_tasks` now routes `tcp://` → DJI binary/text, `file://` → DJI replay, `DJI_TCP_PORT` set → DJI listener.
- Added DJI constants: `DEFAULT_DJI_FEED_URL`, `DEFAULT_DJI_TEXT_FEED_URL`, `DEFAULT_DJI_*_PORT`, etc.
- Backward-compat aliases: `NetWorker`, `BinaryNetWorker`, `TextNetWorker`, `FileReplayWorker`, `TCPListenerWorker`.

## DroneCOT 1.2.0

- Add native Linux wireless Remote ID capture: Wi-Fi monitor mode (Beacon + NAN)
  and BLE via Sniffle-compatible dongle (`wifi://`, `ble://`, `wireless://` feeds).
- Add `rid_normalize`, `wifi_parse`, `wifi_capture`, `ble_parse`, and `ble_capture`
  modules; optional `pip install 'dronecot[wireless]'` for Scapy.

## DroneCOT 1.1.3

- Add user-systemd instance template (`dronecot@.service`) to support running
  serial and MQTT DroneCOT workers side-by-side with layered defaults files.

## DroneCOT 1.1.2

- Unfixes #2.

## DroneCOT 1.1.1

- Fixes #2: Missing cot_to_xml function export.

## DroneCOT 1.1.0

* Updates


## DroneCOT 1.0.0

Initial release of DroneCOT.
