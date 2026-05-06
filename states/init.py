"""
init.py -- перший стан після boot АБО після прокидання зі sleep.

Завдання:
    1. Завантажити settings.json з flash.
    2. Якщо файл відсутній → перший запуск, йдемо одразу в Configuration.
    3. Якщо файл є -- читаємо кнопку:
         - не натиснута            → Diagnostics (нормальний робочий цикл)
         - 3-8 сек затиск          → Configuration (AP)
         - 8-13 сек затиск         → ConfigurationWiFi (STA + дашборд через
                                     домашню Wi-Fi)
         - 13-60 сек затиск        → FactoryReset
         - 60+ сек                 → залипла кнопка, ігноруємо, нормальний цикл

LED під час очікування міняє колір -- наочна підказка користувачу,
яку гілку він зараз обирає:
    зелений → cyan (3с) → blue (8с) → orange (13с)
"""

import time

from .state import AbstractState
from .diagnostics import Diagnostics
from .configuration import Configuration
from .configuration_wifi import ConfigurationWiFi
from .factory_reset import FactoryReset
from constants import (
    SHORT_PRESS_DURATION, WIFI_PRESS_DURATION,
    LONG_PRESS_DURATION, STUCK_BUTTON_DURATION,
)
from helpers import read_settings, sync_time_from_rtc
from models.settings import Settings


class Init(AbstractState):

    def enter(self):
        print(">> Init State")
        self.device.set_led("alive")

    def exec(self):
        try:
            self.device.settings = read_settings()
            self.device.settings_missing = False
        except OSError:
            self.device.settings = Settings()
            self.device.settings_missing = True
            sync_time_from_rtc()
            print(">> No settings.json found -- first setup requires Configuration AP")
            self.device.change_state(Configuration(self.device))
            return

        sync_time_from_rtc()

        button = self.device.button

        if button.value() != 0:
            self.device.change_state(Diagnostics(self.device))
            return

        start_time = time.time()
        stuck = False

        while button.value() == 0:
            elapsed = time.time() - start_time

            if elapsed >= STUCK_BUTTON_DURATION:
                print(f">> Button stuck for {elapsed:.0f}s -- ignoring, going to normal cycle")
                stuck = True
                break

            if elapsed >= LONG_PRESS_DURATION:
                self.device.set_led("factory_reset")
            elif elapsed >= WIFI_PRESS_DURATION:
                self.device.set_led("config_sta")
            elif elapsed >= SHORT_PRESS_DURATION:
                self.device.set_led("config_ap")

            time.sleep_ms(50)

        if stuck:
            self.device.change_state(Diagnostics(self.device))
            return

        held_time = time.time() - start_time

        if held_time >= LONG_PRESS_DURATION:
            self.device.change_state(FactoryReset(self.device))
        elif held_time >= WIFI_PRESS_DURATION:
            wifi_settings = self.device.settings.wifi_settings
            if not wifi_settings.ssid:
                print(">> Wi-Fi dashboard requested, but SSID is empty -- going to Configuration AP")
                self.device.change_state(Configuration(self.device))
            else:
                self.device.change_state(ConfigurationWiFi(self.device))
        elif held_time >= SHORT_PRESS_DURATION:
            self.device.change_state(Configuration(self.device))
        else:
            self.device.change_state(Diagnostics(self.device))

    def leave(self):
        self.device.led_off()
