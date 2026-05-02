"""
factory_reset.py -- видалення налаштувань і повернення пристрою до заводського стану.

Workflow:
    1. Видаляємо settings.json (видаляє Wi-Fi, MQTT, password hash).
    2. Видаляємо measurements.csv і unsent.csv (історія недоречна без контексту).
    3. machine.reset() -- пристрій reboot-иться як свіжий: settings.json
       не знайдеться, Init одразу зайде в Configuration mode.

Користувач отримує "fresh state" пристрій -- як з коробки.
"""

import os
import time
import machine

from .state import AbstractState
from constants import (
    SETTINGS_FILE, MEASUREMENTS_FILE, UNSENT_FILE,
)


class FactoryReset(AbstractState):

    def enter(self):
        print(">> FactoryReset State")
        self.device.set_led("factory_reset")

    def exec(self):
        for path in (SETTINGS_FILE, MEASUREMENTS_FILE, UNSENT_FILE):
            try:
                os.remove(path)
                print(f"removed: {path}")
            except OSError:
                print(f"already absent: {path}")

        time.sleep(2)
        print("Performing controlled reset...")
        machine.reset()

    def leave(self):
        self.device.led_off()
