# Configuration

DroneCOT reads a `[dronecot]` INI section or equivalent environment variables (PyTAK convention: ALL CAPS). Environment variables override values in the config file.

**Example `config.ini`:**

```ini
[dronecot]
FEED_URL = mqtt://broker.example.net:1883
MQTT_TOPIC = #
COT_URL = udp+wo://239.2.3.1:6969
```

**Equivalent environment variables:**

```sh
export FEED_URL=mqtt://broker.example.net:1883
export MQTT_TOPIC='#'
export COT_URL=udp+wo://239.2.3.1:6969
```

A full commented template is in [example-config.ini](https://github.com/snstac/dronecot/blob/main/example-config.ini) in the repository.

---

## Input feed

### `FEED_URL`

**Default:** `serial:///dev/ttyACM0:115200`

Selects the input worker. DroneCOT inspects the URL scheme:

| URL pattern | Worker | Description |
|-------------|--------|-------------|
| `mqtt://host:port` | MQTT | Plain MQTT broker |
| `mqtts://host:port` | MQTT | MQTT over TLS (port 8883 if omitted) |
| `serial:///dev/ttyACM0:115200` | Serial | MAVLink serial Open Drone ID |
| `wifi://wlan0` | Wi-Fi | Linux monitor mode (Beacon + NAN) |
| `wifi+pcap:///path/file.pcapng` | Wi-Fi | Offline pcap replay |
| `ble:///dev/ttyUSB0` or `ble://auto` | BLE | Sniffle USB dongle |
| `wireless://wlan0` | Wi-Fi + BLE | Both workers (set `BLE_SERIAL` if needed) |

!!! note
    Worker selection is based on substrings in `FEED_URL` (`wireless` is checked before `wifi`). See [Feeds](feeds.md).

**Serial URL forms:**

- `serial:///dev/ttyACM1:115200` — device path and baud in the path
- `serial:///dev/ttyACM1` — baud from `SERIAL_BAUD_RATE` or default `115200`

### `SERIAL_PORT`

**Default:** parsed from `FEED_URL`, else `/dev/ttyACM0`

Override the serial device path.

### `SERIAL_BAUD_RATE`

**Default:** parsed from `FEED_URL`, else `115200`

Override the serial baud rate.

---

## Wi-Fi (monitor mode)

Used when `FEED_URL` contains `wifi` or `wireless`.

| Key | Default | Description |
|-----|---------|-------------|
| `WIFI_INTERFACE` | from `FEED_URL` or `wlan0` | Monitor-mode interface |
| `WIFI_CHANNEL` | `6` | Initial channel |
| `WIFI_HOP_CHANNELS` | — | Comma-separated hop list (e.g. `6,149`) |
| `WIFI_HOP_DWELL` | `3,1` | Dwell seconds per channel in hop pair |
| `WIFI_PCAP` | — | Offline pcap path (overrides live capture) |

Requires `pip install 'dronecot[wifi]'` and Linux capabilities for live capture.

---

## BLE (Sniffle)

Used when `FEED_URL` contains `ble` or `wireless`.

| Key | Default | Description |
|-----|---------|-------------|
| `BLE_SERIAL` | `auto` | Serial device path |
| `BLE_BAUD_RATE` | `2000000` | Sniffle baud rate |
| `BLE_LONG_RANGE` | `1` | Listen for BLE 5 Coded PHY |
| `BLE_EXTENDED` | `1` | Extended advertising |

Requires [Sniffle](https://github.com/nccgroup/Sniffle) Python CLI on `PYTHONPATH`.

---

## MQTT

Used when `FEED_URL` contains `mqtt`. Broker host and port are taken from `FEED_URL` (not separate `MQTT_BROKER` / `MQTT_PORT` variables).

| Key | Default | Description |
|-----|---------|-------------|
| `MQTT_TOPIC` | `#` | Subscription topic |
| `MQTT_USERNAME` | — | Broker username |
| `MQTT_PASSWORD` | — | Broker password |
| `MQTT_CLIENT_ID` | `dronecot_{hostname}` | MQTT client ID |

### MQTT TLS

MQTT TLS is **independent** from PyTAK TAK TLS (`PYTAK_TLS_*`). Use `MQTT_TLS_*` for the broker connection.

| Key | Description |
|-----|-------------|
| `MQTT_TLS_CLIENT_CERT` | Client certificate path |
| `MQTT_TLS_CLIENT_KEY` | Client private key path |
| `MQTT_TLS_CLIENT_CAFILE` | CA bundle for broker verification |
| `MQTT_TLS_CLIENT_CIPHERS` | Optional cipher list |
| `MQTT_TLS_DONT_VERIFY` | `1` to disable certificate verification |
| `MQTT_TLS_DONT_CHECK_HOSTNAME` | `1` to skip hostname check |

TLS is also enabled when `FEED_URL` uses `mqtts`/`ssl` or port `8883`.

Certificate paths are resolved relative to the current directory, home directory, and `~/work/SNS/dronecot/`.

See [Feeds](feeds.md) for expected MQTT message formats.

---

## CoT output and identity

| Key | Default | Description |
|-----|---------|-------------|
| `COT_URL` | `udp+wo://239.2.3.1:6969` (PyTAK) | CoT destination |
| `SENSOR_ID` | `dronecot_{hostname}` | Sensor identifier in CoT |
| `SENSOR_COT_TYPE` | `a-f-G-E-S-E` | CoT type for sensor status events |
| `OP_COT_TYPE` | `a-u-G` | CoT type for operator markers |
| `UAS_COT_TYPE` | `a-u-A-M-H-Q` | CoT type for aircraft markers |
| `COT_STALE` | `3600` (PyTAK) | Stale time in seconds |
| `COT_HOST_ID` | `pytak@{hostname}` (PyTAK) | Host ID in remarks |
| `GPS_INFO_CMD` | `gpspipe --json -n 5` | Command for sensor GPS when not in feed |

---

## Optional

| Key | Default | Description |
|-----|---------|-------------|
| `DEBUG` | `0` | Verbose logging (`1`, `true`, `yes`) |
| `ENABLE_RX_MOCK` | `0` | Enable legacy RX mock worker (compatibility) |

---

## PyTAK transport / TLS

DroneCOT uses PyTAK for CoT networking. See the [PyTAK configuration guide](https://pytak.rtfd.io/en/latest/configuration/) for:

- `COT_URL` schemes (`tcp://`, `tls://`, `udp+wo://`, `log://stdout`, etc.)
- `TAK_PROTO`, `PREF_PACKAGE`, `IMPORT_OTHER_CONFIGS`
- `PYTAK_TLS_CLIENT_CERT`, `PYTAK_TLS_CLIENT_KEY`, and related **TAK Server** TLS options

!!! warning
    Do not confuse `PYTAK_TLS_*` (TAK Server / CoT) with `MQTT_TLS_*` (MQTT broker).
