# Quick Start

Get Remote ID data onto the TAK network in a few minutes.

## 1. Install DroneCOT

=== "pip"

    ```sh
    python3 -m pip install dronecot
    ```

=== "Debian / Ubuntu"

    ```sh
    sudo apt update
    wget https://github.com/snstac/pytak/releases/latest/download/python3-pytak_latest_all.deb
    sudo apt install -f ./python3-pytak_latest_all.deb
    wget https://github.com/snstac/dronecot/releases/latest/download/python3-dronecot_latest_all.deb
    sudo apt install -f ./python3-dronecot_latest_all.deb
    ```

See [Installation](installation.md) for developer setup and dependencies.

## 2. Configure

Create `config.ini` for your input feed.

=== "MQTT"

    ```ini
    [dronecot]
    FEED_URL = mqtt://broker.example.net:1883
    MQTT_TOPIC = #
    COT_URL = udp+wo://239.2.3.1:6969
    ```

=== "Serial (MAVLink)"

    ```ini
    [dronecot]
    FEED_URL = serial:///dev/ttyACM0:115200
    COT_URL = udp+wo://239.2.3.1:6969
    ```

=== "Wi-Fi (Linux)"

    ```sh
    pip install 'dronecot[wifi]'
    sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' "$(readlink -f "$(which python3)")"
    ```

    ```ini
    [dronecot]
    FEED_URL = wifi://wlan0
    WIFI_CHANNEL = 6
    COT_URL = udp+wo://239.2.3.1:6969
    ```

=== "BLE (Sniffle)"

    ```ini
    [dronecot]
    FEED_URL = ble://auto
    COT_URL = udp+wo://239.2.3.1:6969
    ```

    Install [Sniffle](https://github.com/nccgroup/Sniffle) and add `python_cli` to `PYTHONPATH`.

For TAK Server over TLS, add PyTAK options — see [Configuration](configuration.md).

## 3. Run

```sh
dronecot -c config.ini
```

Enable debug logging:

```sh
DEBUG=1 dronecot -c config.ini
```

## 4. Run as a service (optional)

- **System unit:** [Usage — systemd](usage.md#run-as-a-service-run-forever)
- **User instances (MQTT + serial side-by-side):** [Usage — user systemd](usage.md#run-side-by-side-with-user-systemd-instances)
