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
