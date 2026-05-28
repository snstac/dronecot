## Command-line

Command-line usage is available by running ``dronecot -h``.

```
usage: dronecot [-h] [-c CONFIG_FILE] [-p PREF_PACKAGE]

options:
  -h, --help            show this help message and exit
  -c CONFIG_FILE, --CONFIG_FILE CONFIG_FILE
                        Optional configuration file. Default: config.ini
  -p PREF_PACKAGE, --PREF_PACKAGE PREF_PACKAGE
                        Optional connection preferences package zip file (aka data package).
```

## Run as a service / Run forever

1. Add the text contents below a file named `/etc/systemd/system/dronecot.service`  
  You can use `nano` or `vi` editors: `sudo nano /etc/systemd/system/dronecot.service`
2. Reload systemctl: `sudo systemctl daemon-reload`
3. Enable DroneCOT: `sudo systemctl enable dronecot`
4. Start DroneCOT: `sudo systemctl start dronecot`

### `dronecot.service` Content
```ini
[Unit]
Description=DroneCOT - Display Drones in TAK
Documentation=https://dronecot.rtfd.io
Wants=network.target
After=network.target
StartLimitIntervalSec=0
# Uncomment this line if you're running dump1090 & dronecot on the same computer:
# After=dump1090-fa.service

[Service]
RuntimeDirectoryMode=0755
ExecStart=/usr/local/bin/dronecot -c /etc/dronecot.ini
SyslogIdentifier=dronecot
Type=simple
Restart=always
RestartSec=30
RestartPreventExitStatus=64
Nice=-5

[Install]
WantedBy=default.target
```

> Pay special attention to the `ExecStart` line above. You'll need to provide the full local filesystem path to both your dronecot executable & dronecot configuration files.

## Run Side-by-Side with user systemd instances

Use the templated user unit at `systemd/user/dronecot@.service` to run multiple
DroneCOT processes on one server (for example one MQTT feed and one serial feed).

1. Install the user unit template:
   - `mkdir -p ~/.config/systemd/user`
   - `cp systemd/user/dronecot@.service ~/.config/systemd/user/`
2. Create optional shared defaults:
   - `mkdir -p ~/.config/dronecot`
   - `nano ~/.config/dronecot/defaults`
3. Create per-instance defaults files:
   - `nano ~/.config/dronecot/mqtt.env`
   - `nano ~/.config/dronecot/serial.env`
4. Reload and start both instances:
   - `systemctl --user daemon-reload`
   - `systemctl --user enable --now dronecot@mqtt dronecot@serial`
5. Check logs:
   - `journalctl --user -fu dronecot@mqtt`
   - `journalctl --user -fu dronecot@serial`

The unit loads defaults files in this order (later files override earlier values):

1. `/etc/default/dronecot` (optional shared system defaults)
2. `/etc/default/dronecot.%i` (optional system instance defaults)
3. `~/.config/dronecot/defaults` (optional shared user defaults)
4. `~/.config/dronecot/%i.env` (optional user instance defaults)

The unit prefers a virtualenv install if available at
`$HOME/work/SNS/dronecot/.venv/bin/dronecot`.
You can override this path with `DRONECOT_BIN=/path/to/dronecot` in any defaults file.

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