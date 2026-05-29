# Requirements

DroneCOT runs on Python **3.9+** on Linux, macOS, and Windows.

## Runtime dependencies

Installed automatically with `pip install dronecot`:

| Package | Purpose |
|---------|---------|
| [PyTAK](https://pytak.rtfd.io) | CoT networking and CLI |
| `aiomqtt` | Async MQTT client |
| `paho-mqtt` | MQTT protocol support |
| `pymavlink` | MAVLink serial (serial feed) |
| `pyserial` | Serial port access |
| `bitstruct` | Open Drone ID message parsing |
| `cryptography` | TLS |
| `aiohttp` | HTTP client support |
| `pytz` | Timezone formatting in CoT remarks |

## Optional

| Extra | Package | Purpose |
|-------|---------|---------|
| `with_takproto` | `takproto` | TAK Protocol (protobuf) CoT payloads |

## System tools

- **`gpspipe`** (optional): used by `GPS_INFO_CMD` for sensor status position when GPS is not embedded in the feed. Typically from the `gpsd` package on Debian/Ubuntu.

## Serial permissions (Linux)

The user running DroneCOT needs read/write access to the serial device (often membership in the `dialout` group):

```sh
sudo usermod -aG dialout $USER
```

Log out and back in after changing group membership.
