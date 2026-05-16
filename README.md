# Frogix

MicroPython firmware for a temperature and humidity monitor with a local web dashboard and MQTT publishing. The device reads a DHT11 sensor, keeps a rolling measurement history and queues readings when they cannot be sent.

## Features

- Browser dashboard with current readings and up to 96 history points, sampled every 15 minutes.
- Wi-Fi and MQTT configuration through a web interface.
- Configurable MQTT publishing interval from one minute to 12 hours.
- Local queue for up to 288 unsent readings.
- Password-protected setup, expiring sessions and login rate limiting.
- Configurable NeoPixel status colors and brightness.
- Settings updates over MQTT.
- Button controls for configuration and factory reset.

## Hardware

The current configuration targets a Raspberry Pi Pico 2 W running MicroPython, with a DHT11, a WS2812 NeoPixel and a push button. GPIO assignments are defined in `constants.py`:

| Component | GPIO |
| --- | --- |
| DHT11 data | 27 |
| NeoPixel data | 18 |
| Button | 20 |

The button uses an internal pull-up and connects to ground when pressed. Check the wiring and GPIO assignments before using another board.

## Getting started

1. Install MicroPython firmware for your board.
2. Copy the root Python files and the `models/`, `sensors/`, `states/`, `web/`, `static/` and `lib/` directories to the device, preserving their structure. Microdot and the MQTT client are included in `lib/`.
3. Restart the board. MicroPython runs `boot.py`, followed by `main.py`.
4. On the first run, connect to the `thsensor` access point and open `http://192.168.4.1`. The default access-point password is defined in `constants.py`; change it in setup.
5. Create the web-interface password, then configure Wi-Fi and your MQTT broker.

During normal operation, hold the button for approximately 3 seconds to open access-point configuration, 8 seconds to open configuration on the existing Wi-Fi network, or 13 seconds to perform a factory reset.

## Project structure

| Path | Purpose |
| --- | --- |
| `boot.py`, `main.py` | Startup |
| `device.py` | Device peripherals and state lifecycle |
| `constants.py` | Pins, timing and defaults |
| `helpers.py` | Settings, timestamps, local storage and authentication helpers |
| `models/` | Settings schema and validation |
| `sensors/` | Sensor interface, drivers and active-sensor registry |
| `states/` | Measurement, networking, configuration and other device states |
| `web/` | HTTP endpoints and asynchronous Wi-Fi helpers |
| `static/` | Dashboard, setup and authentication pages |
| `lib/` | Bundled Microdot and umqtt libraries |

Runtime settings and measurements are stored in `settings.json`, `measurements.jsonl` and `unsent.jsonl`. These files are excluded from Git.

To add a sensor, implement the interface in `sensors/base.py`, register the driver in `sensors/__init__.py` and add any new metric units in `constants.py`.

The firmware uses MicroPython hardware modules and runs on the board. Opening the HTML files on a computer does not provide live sensor data.
