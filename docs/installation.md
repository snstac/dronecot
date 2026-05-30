# Installation

DroneCOT is a command-line program: `dronecot`.

## Requirements

- Python 3.9 or newer
- [PyTAK](https://pytak.rtfd.io) 5.4.0+
- For MQTT feeds: `aiomqtt`, `paho-mqtt`
- For serial MAVLink feeds: `pymavlink`, `pyserial`
- Open Drone ID parsing: `bitstruct`

All runtime dependencies are installed automatically with `pip install dronecot`.

## Debian / Ubuntu / Raspberry Pi

Install PyTAK and DroneCOT from GitHub releases:

```sh linenums="1"
sudo apt update
wget https://github.com/snstac/pytak/releases/latest/download/python3-pytak_latest_all.deb
sudo apt install -f ./python3-pytak_latest_all.deb
wget https://github.com/snstac/dronecot/releases/latest/download/python3-dronecot_latest_all.deb
sudo apt install -f ./python3-dronecot_latest_all.deb
```

## pip (all platforms)

```sh
python3 -m pip install dronecot
```

Optional extras:

```sh
python3 -m pip install 'dronecot[with_takproto]'
python3 -m pip install 'dronecot[wireless]'   # Wi-Fi monitor (Scapy) + BLE (Sniffle separately)
```

## Developers

```sh linenums="1"
git clone https://github.com/snstac/dronecot.git
cd dronecot/
make setup
.venv/bin/dronecot -c example-config.ini
```

`make setup` creates a virtualenv and installs dependencies from `requirements.txt`.

Install the user systemd template:

```sh
make install_user_systemd
```

## Next steps

- [Quick Start](quickstart.md)
- [Configuration](configuration.md)
- [Usage](usage.md)
