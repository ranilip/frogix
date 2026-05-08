"""
device.py -- клас Device, кореневий обʼєкт пристрою.

Тримає:
    - hardware peripherals (LED, button, далі: dht, mqtt, wlan...)
    - поточний стан state machine
    - завантажені налаштування (Settings)

Надає:
    Device.run() -- головний цикл життєвого циклу станів
    Device.change_state(new_state) -- заявка на перехід
"""

import time

import network
from machine import Pin
from neopixel import NeoPixel

from constants import NP_PIN, BTN_PIN, LED_ROLE_DEFAULTS
from states.init import Init


class Device:
    def __init__(self):
        self.led = NeoPixel(Pin(NP_PIN, Pin.OUT), 1)

        self.button = Pin(BTN_PIN, Pin.IN, Pin.PULL_UP)

        self.state = Init(self)

        self.settings = None
        self.settings_missing = False

        from sensors import ALL as _SENSORS
        self.sensors = _SENSORS

        self.wlan = network.WLAN(network.STA_IF)

        self.mqtt_client = None

        self.last_wifi_status = 'unknown'
        self.last_mqtt_status = 'unknown'

        self.boot_time = time.time()

        self.last_mqtt_attempt_at = 0

        self.current_led_role = None

    def run(self):
        """
        Головний цикл state machine.

        Виконує lifecycle поточного стану: enter → exec → leave.
        Якщо під час exec() стан викликав change_state() -- self.state
        вказує на новий стан, і цикл переходить до нього.
        Якщо exec() завершився без зміни state -- цикл зупиняється.
        """
        try:
            while self.state is not None:
                current = self.state

                current.enter()
                current.exec()
                current.leave()

                if self.state is current:
                    self.state = None

        except SystemExit:
            print(">> Device exit via SystemExit")

        print("Device run finished")

    def change_state(self, new_state):
        """
        Заявка на перехід у новий стан.

        Не викликає enter() новго стану одразу -- лише виставляє self.state.
        Реальний перехід відбувається у run() після того, як exec() і leave()
        поточного стану повернуть управління.
        """
        self.state = new_state

    def led_color(self, role):
        """Return runtime RGB tuple for a configured LED role."""
        cfg = None
        if self.settings is not None:
            led_settings = getattr(self.settings, "led_settings", None)
            if led_settings is not None and hasattr(led_settings, role):
                cfg = getattr(led_settings, role)

        if cfg is None:
            fallback = LED_ROLE_DEFAULTS.get(role, LED_ROLE_DEFAULTS["alive"])
            color = fallback["color"]
            brightness = fallback["brightness"]
        else:
            color = cfg.color
            brightness = cfg.brightness

        try:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
        except Exception:
            return (0, 0, 0)

        scale = max(0, min(100, int(brightness))) / 100
        return (int(r * scale), int(g * scale), int(b * scale))

    def set_led(self, role):
        """Set NeoPixel color by configured role name."""
        self.current_led_role = role
        self.led[0] = self.led_color(role)
        self.led.write()

    def preview_led(self, color, brightness):
        """Temporarily set NeoPixel to arbitrary #RRGGBB + brightness."""
        try:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            scale = max(0, min(100, int(brightness))) / 100
            self.led[0] = (int(r * scale), int(g * scale), int(b * scale))
            self.led.write()
        except Exception:
            pass

    def restore_led_indicator(self):
        """Return NeoPixel to the current state indicator after preview."""
        if self.current_led_role:
            self.set_led(self.current_led_role)
        else:
            self.led_off()

    def led_off(self):
        """Turn NeoPixel off."""
        self.current_led_role = None
        self.led[0] = (0, 0, 0)
        self.led.write()
