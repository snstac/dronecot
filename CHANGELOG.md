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
