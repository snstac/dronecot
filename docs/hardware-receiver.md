# Wi-Fi & BLE Hardware Receiver Setup

Build a standalone Remote ID receiver that detects drone broadcasts over 802.11 Wi-Fi and Bluetooth Low Energy (BLE) and streams UAS tracks to TAK mesh SA in real time.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Linux host (Raspberry Pi or x86)           │
│                                             │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Wi-Fi adapter│  │ BLE sniffer dongle   │ │
│  │ (monitor)    │  │ (Sniffle firmware)   │ │
│  └──────┬───────┘  └──────────┬───────────┘ │
│         │                     │             │
│         └──────────┬──────────┘             │
│                    ▼                        │
│              dronecot                       │
│          (wireless:// feed)                 │
│                    │                        │
│                    ▼                        │
│        CoT XML → TAK mesh SA               │
│       udp+wo://239.2.3.1:6969              │
└─────────────────────────────────────────────┘
```

Remote ID under ASTM F3411 / FAA Part 89 is broadcast over:

- **Wi-Fi Beacon** — 802.11 management frames with ASTM vendor IE (OUI `FA:0B:BC`), channels 1/6/11
- **Wi-Fi NAN** (Neighbor Awareness Networking) — 802.11 action frames on social channels 6/44/149
- **BLE** — Bluetooth 5 extended advertisements and legacy advertisements

---

## Hardware

### Wi-Fi adapter

The adapter must support **monitor mode** on Linux. Chipsets with reliable mainline driver support:

| Chipset | Driver | Notes |
|---------|--------|-------|
| MediaTek MT7612U | `mt76` | Recommended; 2.4 + 5 GHz; Alfa AWUS036ACM |
| MediaTek MT7610U | `mt76` | Alfa AWUS036ACHM, TP-Link T2U Plus |
| Realtek RTL8812AU | `rtl8812au`¹ | Alfa AWUS036ACH, Netgear A6210 |
| Ralink RT5572 | `rt2800usb` | Dual-band; widely available |
| Raspberry Pi BCM43438 | `brcmfmac` | Pi 3/4/Zero W onboard — 2.4 GHz only |

¹ The in-kernel driver may not support monitor mode; use the [aircrack-ng fork](https://github.com/aircrack-ng/rtl8812au).

Remote ID Beacon and NAN frames are primarily on 2.4 GHz. A 2.4 GHz-only adapter is sufficient for most deployments. For 5 GHz NAN coverage, use a dual-band adapter and enable channel hopping.

### BLE sniffer dongle

DroneCOT uses [Sniffle](https://github.com/nccgroup/Sniffle) for BLE capture. Compatible hardware:

| Board | Chip | Notes |
|-------|------|-------|
| Nordic nRF52840 Dongle (PCA10059) | nRF52840 | ~$10; recommended |
| Nordic nRF52840 DK | nRF52840 | Dev kit; ~$40 |
| Makerdiary nRF52840 MDK USB Dongle | nRF52840 | |
| Sonoff Zigbee 3.0 USB Dongle Plus | CC2652P | Also Sniffle-compatible |

All boards must be flashed with Sniffle firmware (see [BLE setup](#ble-setup)).

---

## Host setup

A Raspberry Pi 4 or Pi 5 running Raspberry Pi OS (64-bit, Bookworm) works well. Any Linux host with Python 3.9+ will do.

### Install DroneCOT

```sh
sudo apt update && sudo apt install -y python3 python3-pip
python3 -m pip install 'dronecot[wireless]'
```

This installs Scapy for Wi-Fi capture. BLE capture requires Sniffle (installed separately — see below).

### Wi-Fi monitor mode

#### Verify the adapter

```sh
iw dev
```

Look for your adapter (e.g., `wlan1`). Confirm monitor mode is listed:

```sh
iw phy phy1 info | grep -A5 "Supported interface modes"
```

`* monitor` must appear in the list.

#### Enable monitor mode

```sh
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
sudo iw dev wlan1 set channel 6
```

To persist across reboots, add a NetworkManager override or use a startup script. Example systemd `ExecStartPre`:

```ini
ExecStartPre=/usr/sbin/ip link set wlan1 down
ExecStartPre=/usr/sbin/iw dev wlan1 set type monitor
ExecStartPre=/usr/sbin/ip link set wlan1 up
ExecStartPre=/usr/sbin/iw dev wlan1 set channel 6
```

#### Grant capture privileges (non-root)

```sh
sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' "$(readlink -f "$(which python3)")"
```

Or run DroneCOT as root (not recommended for long-term deployments).

!!! note
    `setcap` must be re-applied after Python upgrades. Wrap it in a `make setup` step if needed.

#### Multi-channel / frequency hopping

For broader coverage, configure DroneCOT to hop between 2.4 GHz channels:

```ini
WIFI_HOP_CHANNELS = 1,6,11
WIFI_HOP_DWELL = 2,2,2
```

For 5 GHz NAN coverage, add channel 44 and 149 with a shorter dwell:

```ini
WIFI_HOP_CHANNELS = 6,44,149
WIFI_HOP_DWELL = 3,1,1
```

### BLE setup

#### Flash Sniffle firmware

1. Download the latest `.hex` from [Sniffle releases](https://github.com/nccgroup/Sniffle/releases).
2. Flash to the nRF52840 dongle:

   ```sh
   pip install nrfutil
   # For Nordic nRF52840 Dongle (PCA10059) — enter DFU mode first (press RESET while connecting)
   nrfutil dfu usb-serial -pkg sniffle_nrf52840dongle_<version>.zip -p /dev/ttyACM0
   ```

   For other boards see the [Sniffle flashing docs](https://github.com/nccgroup/Sniffle#device-setup).

#### Install Sniffle Python CLI

Sniffle is GPLv3 and distributed separately. DroneCOT invokes it at runtime:

```sh
git clone https://github.com/nccgroup/Sniffle.git ~/sniffle
echo "export PYTHONPATH=\"\$PYTHONPATH:$HOME/sniffle/python_cli\"" >> ~/.bashrc
source ~/.bashrc
```

Confirm the dongle is visible:

```sh
ls /dev/ttyACM*   # or /dev/ttyUSB*
```

---

## Configuration

### Wi-Fi only

```ini
[dronecot]
FEED_URL = wifi://wlan1
WIFI_CHANNEL = 6
COT_URL = udp+wo://239.2.3.1:6969
```

### BLE only

```ini
[dronecot]
FEED_URL = ble:///dev/ttyACM0
BLE_BAUD_RATE = 2000000
BLE_LONG_RANGE = 1
BLE_EXTENDED = 1
COT_URL = udp+wo://239.2.3.1:6969
```

Use `ble://auto` to let DroneCOT find the dongle automatically.

### Wi-Fi + BLE combined (recommended)

```ini
[dronecot]
FEED_URL = wireless://wlan1
BLE_SERIAL = /dev/ttyACM0
WIFI_CHANNEL = 6
BLE_BAUD_RATE = 2000000
BLE_LONG_RANGE = 1
BLE_EXTENDED = 1
COT_URL = udp+wo://239.2.3.1:6969
```

`wireless://` starts both `WifiWorker` and `BleWorker` with a single `RIDWorker` consuming both.

### TAK Server instead of mesh SA

Replace `COT_URL` with your TAK Server address:

```ini
COT_URL = tcp://tak-server.example.net:8089
```

For TLS-authenticated TAK Server connections, see [PyTAK TLS configuration](https://pytak.rtfd.io).

### Sensor identity (optional)

```ini
SENSOR_ID = CUAS-ALPHA-01
COT_HOST_ID = pi-receiver-01
```

`SENSOR_ID` appears in the `__cuas` CoT detail element and in ATAK track remarks.

---

## Run as a service

### System-level (single feed)

Create `/etc/systemd/system/dronecot-wireless.service`:

```ini
[Unit]
Description=DroneCOT Wi-Fi + BLE Remote ID receiver
Documentation=https://dronecot.rtfd.io
After=network.target

[Service]
ExecStartPre=/usr/sbin/ip link set wlan1 down
ExecStartPre=/usr/sbin/iw dev wlan1 set type monitor
ExecStartPre=/usr/sbin/ip link set wlan1 up
ExecStartPre=/usr/sbin/iw dev wlan1 set channel 6
ExecStart=/usr/local/bin/dronecot -c /etc/dronecot-wireless.ini
EnvironmentFile=-/etc/default/dronecot-wireless
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now dronecot-wireless
sudo journalctl -fu dronecot-wireless
```

### User instances (multiple feeds side-by-side)

Use the bundled user unit template to run a wireless receiver and a DJI AntSDR feed simultaneously:

```sh
make install_user_systemd
```

```sh
# ~/.config/dronecot/wireless.env
FEED_URL=wireless://wlan1
BLE_SERIAL=/dev/ttyACM0
WIFI_CHANNEL=6
COT_URL=udp+wo://239.2.3.1:6969
SENSOR_ID=CUAS-WIRELESS-01

# ~/.config/dronecot/antsdr.env
FEED_URL=tcp://192.168.1.10:41030
COT_URL=udp+wo://239.2.3.1:6969
SENSOR_ID=CUAS-ANTSDR-01
DJI_SENSOR_NAME=AntSDR-Alpha
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now dronecot@wireless dronecot@antsdr
```

The user unit may need extra capabilities for raw socket access. Add to `~/.config/systemd/user/dronecot@.service`:

```ini
[Service]
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
```

---

## Raspberry Pi deployment tips

- Use **Raspberry Pi OS Lite (64-bit)** to minimize overhead.
- Place the config in `/boot/firmware/dronecot.ini` for easy access from the SD card on another machine.
- Power the Pi and both USB peripherals from a powered hub if the combined draw exceeds ~900 mA.
- For field deployments, consider a [USB LTE modem](https://www.raspberrypi.com/products/) and `COT_URL=tcp://tak-server.example.net:8089` to push tracks to a remote TAK Server.
- Onboard Wi-Fi (`wlan0`) can be used for management/SSH; dedicate a USB adapter (`wlan1`) to monitor mode.

---

## Verifying output

Enable debug logging to confirm frames are being decoded:

```sh
DEBUG=1 dronecot -c config.ini
```

Look for lines like:

```
dronecot - INFO - RID UAS CoT: uid=RID.1787F04BM24010011195.uas type=a-n-A-M-H-Q
```

In ATAK, Remote ID tracks appear as blue UAS icons with call signs, position, speed, and altitude. Tap a track to see MAC address, RSSI, channel, and sensor ID in the remarks.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No Wi-Fi frames | `iw dev wlan1 info` — confirm `type monitor`; try `sudo` |
| `SIOCSIFFLAGS: Operation not permitted` | NetworkManager managing the adapter — `nmcli dev set wlan1 managed no` |
| No BLE frames | Confirm Sniffle firmware version matches Python CLI version |
| `ModuleNotFoundError: sniffle` | `PYTHONPATH` not set — add `sniffle/python_cli` |
| Tracks appear then vanish | Increase `COT_STALE` (default 60 s) — `COT_STALE = 300` |
| Duplicate tracks | Multiple dronecot instances on same multicast — expected behavior |

See [Troubleshooting](troubleshooting.md) for additional debug options.
