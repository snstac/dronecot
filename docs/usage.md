# Usage

## Command-line

```sh
dronecot -h
```

```
usage: dronecot [-h] [-c CONFIG_FILE] [-p PREF_PACKAGE]

options:
  -h, --help            show this help message and exit
  -c CONFIG_FILE, --CONFIG_FILE CONFIG_FILE
                        Optional configuration file. Default: config.ini
  -p PREF_PACKAGE, --PREF_PACKAGE PREF_PACKAGE
                        Optional connection preferences package zip file (aka data package).
```

Configuration parameters are documented in [Configuration](configuration.md). See [Quick Start](quickstart.md) for a minimal `config.ini`.

## Run as a service / Run forever

1. Create `/etc/systemd/system/dronecot.service` (e.g. `sudo nano /etc/systemd/system/dronecot.service`).
2. `sudo systemctl daemon-reload`
3. `sudo systemctl enable dronecot`
4. `sudo systemctl start dronecot`

### `dronecot.service` content

```ini
[Unit]
Description=DroneCOT - Display Drones in TAK
Documentation=https://dronecot.rtfd.io
Wants=network.target
After=network.target
StartLimitIntervalSec=0

[Service]
RuntimeDirectoryMode=0755
ExecStart=/usr/local/bin/dronecot -c /etc/dronecot.ini
EnvironmentFile=-/etc/default/dronecot
SyslogIdentifier=dronecot
Type=simple
Restart=always
RestartSec=30
RestartPreventExitStatus=64
Nice=-5

[Install]
WantedBy=multi-user.target
```

!!! tip
    Adjust `ExecStart` to the full path of your `dronecot` binary and config file. On Debian packages, the binary is often `/usr/bin/dronecot`.

Example `/etc/default/dronecot`:

```bash
FEED_URL=mqtt://broker.example.net:1883
MQTT_TOPIC=#
COT_URL=udp+wo://239.2.3.1:6969
```

## Run side-by-side with user systemd instances

Use the templated user unit at [`systemd/user/dronecot@.service`](https://github.com/snstac/dronecot/blob/main/systemd/user/dronecot@.service) to run multiple DroneCOT processes on one host (for example one MQTT feed and one serial feed).

1. Install the user unit template:
   ```sh
   mkdir -p ~/.config/systemd/user
   cp systemd/user/dronecot@.service ~/.config/systemd/user/
   ```
   Or: `make install_user_systemd`
2. Create optional shared defaults:
   ```sh
   mkdir -p ~/.config/dronecot
   nano ~/.config/dronecot/defaults
   ```
3. Create per-instance env files:
   ```sh
   nano ~/.config/dronecot/mqtt.env
   nano ~/.config/dronecot/serial.env
   ```
4. Reload and start:
   ```sh
   systemctl --user daemon-reload
   systemctl --user enable --now dronecot@mqtt dronecot@serial
   ```
5. Logs:
   ```sh
   journalctl --user -fu dronecot@mqtt
   journalctl --user -fu dronecot@serial
   ```

Environment files are loaded in order (later overrides earlier):

1. `/etc/default/dronecot` (optional shared system defaults)
2. `/etc/default/dronecot.%i` (optional system instance defaults)
3. `~/.config/dronecot/defaults` (optional shared user defaults)
4. `~/.config/dronecot/%i.env` (per-instance)

The unit prefers `$DRONECOT_WORKDIR/.venv/bin/dronecot` when executable, then `dronecot` on `PATH`, then `/usr/bin/dronecot`. Override with `DRONECOT_BIN` in any env file.

### Example `~/.config/dronecot/mqtt.env`

```bash
FEED_URL=mqtt://broker.example.net:1883
MQTT_TOPIC=#
COT_URL=udp+wo://239.2.3.1:6969
DEBUG=1
```

### Example `~/.config/dronecot/serial.env`

```bash
FEED_URL=serial:///dev/ttyACM1:115200
COT_URL=udp+wo://239.2.3.1:6969
DEBUG=1
```

See [Troubleshooting](troubleshooting.md) for debug logging and common issues.
