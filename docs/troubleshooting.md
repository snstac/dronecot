# Troubleshooting

## Enable debug logging

```sh
DEBUG=1 dronecot -c config.ini
```

Or in `config.ini`:

```ini
[dronecot]
DEBUG = 1
```

## systemd logs

System service:

```sh
journalctl -fu dronecot
```

User instance (e.g. MQTT worker):

```sh
journalctl --user -fu dronecot@mqtt
```

Per-instance log files (user template): `$XDG_RUNTIME_DIR/dronecot/<instance>.log`

## MQTT

| Symptom | Things to check |
|---------|-----------------|
| No connection | `FEED_URL` host/port; firewall; `MQTT_USERNAME` / `MQTT_PASSWORD` |
| TLS failures | `MQTT_TLS_*` paths; use `MQTT_TLS_DONT_VERIFY=1` only for testing |
| No aircraft | `MQTT_TOPIC` matches publisher; message format — see [Feeds](feeds.md) |
| Wrong TLS stack | MQTT uses `MQTT_TLS_*`, not `PYTAK_TLS_*` |

Test with debug logging and confirm `Connected to MQTT Broker` and `Subscribed to topic` appear in logs.

## Serial / MAVLink

| Symptom | Things to check |
|---------|-----------------|
| Permission denied | User in `dialout` group; device path in `FEED_URL` or `SERIAL_PORT` |
| Heartbeat timeout | Correct baud rate; cable; device powered; try `SERIAL_BAUD_RATE` override |
| No ODID events | Autopilot must emit `OPEN_DRONE_ID_MESSAGE_PACK`; other MAVLink traffic is ignored |

DroneCOT reconnects automatically after serial or heartbeat errors.

## CoT / TAK

| Symptom | Things to check |
|---------|-----------------|
| Nothing in ATAK | `COT_URL` reachable; multicast interface; TAK Server TLS certs (`PYTAK_TLS_*`) |
| Sensor only, no drones | Feed publishing status vs. position topics — see [Feeds](feeds.md) |

Use `COT_URL=log://stdout` to print CoT XML locally (PyTAK debug destination).

## Support

Please use [GitHub issues](https://github.com/snstac/dronecot/issues) for bug reports. Include debug logs with secrets redacted.

DroneCOT is free open source software with no warranty. See [License](license.md).
