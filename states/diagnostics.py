"""
diagnostics.py -- self-test усіх зареєстрованих сенсорів при boot.

Завдання:
    1. Викликати setup() на кожному сенсорі (lazy hardware init).
    2. Спробувати прочитати з кожного -- verify що відповідає.
    3. До DHT_RETRY_COUNT спроб з паузою (для повільних сенсорів типу DHT11).
    4. ОК → Measurement. Невдача → Error.

Якщо ХОЧА Б ОДИН сенсор фейлить -- переходимо в Error. Це консервативний
вибір: краще reboot і повторна спроба, ніж публікувати неповні дані.
"""

import time

from .state import AbstractState
from .measurement import Measurement
from .error import Error
from constants import DHT_RETRY_COUNT, DHT_RETRY_DELAY


class Diagnostics(AbstractState):

    def enter(self):
        print(">> Diagnostics State")
        self.device.set_led("measurement")

        for sensor in self.device.sensors:
            try:
                sensor.setup()
            except Exception as e:
                print(f"Sensor {sensor.name} setup failed: {e}")

    def exec(self):
        for attempt in range(1, DHT_RETRY_COUNT + 1):
            try:
                for sensor in self.device.sensors:
                    sensor.read()

                print(f"All sensors OK (attempt {attempt}/{DHT_RETRY_COUNT})")
                self.device.change_state(Measurement(self.device))
                return

            except Exception as e:
                print(f"Sensor self-test attempt {attempt}/{DHT_RETRY_COUNT} failed: {e}")
                time.sleep(DHT_RETRY_DELAY)

        print("All sensor attempts failed -- going to Error")
        self.device.change_state(Error(self.device))

    def leave(self):
        self.device.led_off()
