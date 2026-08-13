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
| `ble+hci://hci0` | BLE | Onboard BlueZ adapter — no extra hardware |
| `wireless://wlan0` | Wi-Fi + BLE | Both workers (set `BLE_SERIAL` if needed) |

!!! note
    Worker selection is based on substrings in `FEED_URL` (`wireless` is checked before `wifi`, and `ble+hci` before `ble`). See [Feeds](feeds.md).

**Serial URL forms:**

- `serial:///dev/ttyACM1:115200` — device path and baud in the path
- `serial:///dev/ttyACM1` — baud from `SERIAL_BAUD_RATE` or default `115200`

### `SERIAL_PORT`

**Default:** parsed from `FEED_URL`, else `/dev/ttyACM0`

Override the serial device path.

### `SERIAL_BAUD_RATE`

**Default:** parsed from `FEED_URL`, else `115200`

Override the serial baud rate.

### `SERIAL_CRLF_NORMALIZE`

**Default:** `0` (disabled)

Set to `1` for a binary MAVLink receiver whose USB serial firmware expands
every LF byte to CRLF. This console-style newline conversion corrupts any
MAVLink frame containing an LF byte in its header, payload, or checksum.
DroneCOT reverses the expansion before passing bytes to pymavlink, including
when a CRLF pair is split across serial reads.

Leave this disabled for standards-compliant binary serial feeds. It is intended
as a compatibility workaround for affected receiver firmware, not as general
MAVLink framing.

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

## BLE (onboard BlueZ adapter)

Used when `FEED_URL` uses the `ble+hci://` scheme. Captures Remote ID on the
Bluetooth radio the board already has — no Sniffle dongle, no extra hardware.

| Key | Default | Description |
|-----|---------|-------------|
| `BLE_ADAPTER` | from `FEED_URL` or `hci0` | BlueZ adapter to use |
| `BLE_READER` | `auto` | `monitor`, `dbus`, or `auto` (see below) |
| `BLE_RSSI_THRESHOLD` | — | Drop advertisements weaker than this (dBm) |

DroneCOT always drives a continuous LE scan over BlueZ D-Bus
(`SetDiscoveryFilter` with `Transport: le`, then `StartDiscovery`). Because that
is an ordinary D-Bus client it **coexists with `bluetoothd` and with an active
Bluetooth PAN** rather than seizing the adapter.

Two ways to read the advertisements:

- **`monitor`** — an `HCI_CHANNEL_MONITOR` socket, the same passive tap `btmon`
  uses. Delivers every advertising report with full advertisement bytes and
  per-frame RSSI, with nothing coalesced. Needs `CAP_NET_RAW`
  (systemd: `AmbientCapabilities=CAP_NET_RAW`).
- **`dbus`** — reads the `ServiceData` property off `org.bluez.Device1`. Needs no
  elevated capability, but BlueZ may coalesce repeated advertisements. For
  Remote ID a coalesced repeat is a lost message *type*, not a duplicate, so
  prefer `monitor` where you can.
- **`auto`** (default) — try `monitor`, fall back to `dbus`.

Query options may also be given in the URL:
`ble+hci://hci0?reader=monitor&rssi=-95&duplicates=1`

!!! warning "Legacy advertising only"
    This path captures **legacy** advertisements. The ASTM long-range profile
    uses BT5 extended advertising on the Coded PHY, which the Raspberry Pi's
    CYW43455 is not known to receive. Treat onboard capture as complementary to
    a Sniffle dongle or a DroneScout receiver, not a replacement.

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

## Remote ID track aggregation

A BLE legacy transmitter fits only **one** 25-byte ODID message per
advertisement, so it rotates through message types: the serial (BasicID), the
aircraft position (Location) and the operator location (System) each arrive in a
*different* frame. DroneCOT merges them per transmitter — keyed on the
advertiser MAC, which ASTM F3411 requires to stay constant for a flight session
— so the CoT it emits carries the serial from one advertisement and the position
from another.

Without this, position-less messages are dropped and position-only messages all
render with the same placeholder UID, collapsing every aircraft in range onto a
single track.

Sources that send a full `0xF` message pack (most Wi-Fi beacons, DroneScout,
MQTT) already carry everything in one frame and are unaffected.

| Key | Default | Description |
|-----|---------|-------------|
| `RID_TRACK_TTL` | `120` | Seconds of silence before a transmitter's track expires. Set `0` to disable aggregation and render every message independently. |
| `RID_TRACK_MAX` | `512` | Hard cap on simultaneously tracked transmitters; least-recently-heard are evicted first. |
| `RID_TRACK_ID_GRACE` | `5` | Seconds to wait for a serial before rendering a position-only track under a MAC-derived UID. Prevents one aircraft appearing as two TAK markers. `0` renders immediately. |

---

## Optional

| Key | Default | Description |
|-----|---------|-------------|
| `DEBUG` | `0` | Verbose logging (`1`, `true`, `yes`) |
| `ENABLE_RX_MOCK` | `0` | Enable legacy RX mock worker (compatibility) |
| `SERIAL_CRLF_NORMALIZE` | `0` | Reverse broken LF-to-CRLF expansion on a binary MAVLink serial feed |

---

## PyTAK transport / TLS

DroneCOT uses PyTAK for CoT networking. See the [PyTAK configuration guide](https://pytak.rtfd.io/en/latest/configuration/) for:

- `COT_URL` schemes (`tcp://`, `tls://`, `udp+wo://`, `log://stdout`, etc.)
- `TAK_PROTO`, `PREF_PACKAGE`, `IMPORT_OTHER_CONFIGS`
- `PYTAK_TLS_CLIENT_CERT`, `PYTAK_TLS_CLIENT_KEY`, and related **TAK Server** TLS options

!!! warning
    Do not confuse `PYTAK_TLS_*` (TAK Server / CoT) with `MQTT_TLS_*` (MQTT broker).
