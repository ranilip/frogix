"""
error.py -- стан помилки.

Призначений для всіх ситуацій, коли пристрій не може продовжити
нормальну роботу: сенсор не відповідає, Wi-Fi не підключається,
MQTT broker недоступний, незловлене виключення.

Workflow:
    1. Червоний LED на 5 секунд (часу подивитись serial console).
    2. machine.reset() -- повний reboot, пристрій стартує з нуля.

Self-recovery: тимчасова поломка (broker помер на 5 хв, Wi-Fi глюкнув)
лікується сама собою -- пристрій reboot-иться, повторює спробу, і якщо
проблема пройшла, продовжує штатну роботу.
"""

import time
import machine

from .state import AbstractState


class Error(AbstractState):

    def enter(self):
        print(">> Error State")
        self.device.set_led("error")

    def exec(self):
        time.sleep(5)
        print("Performing controlled reset...")
        machine.reset()

    def leave(self):
        self.device.led_off()
