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
