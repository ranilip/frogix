"""
state.py -- базовий клас для всіх станів пристрою.

Усі реальні стани (Init, Configuration, Measurement, Sleep тощо)
наслідуються від AbstractState і реалізують свою логіку в enter/exec/leave.
"""


class AbstractState:
    """
    Базовий клас стану.

    Кожен стан має життєвий цикл з трьох фаз:
        enter() -- викликається один раз при вході в стан.
                  Сюди йде налаштування ресурсів (увімкнути LED, відкрити порт).
        exec()  -- основна робота стану. Може кликати device.change_state(...)
                  для переходу. Може блокуватись надовго (наприклад, web server).
        leave() -- викликається один раз перед виходом зі стану.
                  Сюди йде звільнення ресурсів (вимкнути LED, закрити порт).

    Усі стани отримують посилання на Device -- через нього вони мають доступ
    до спільних ресурсів (LED, settings, network) і можуть викликати
    change_state() для переходу на інший стан.
    """

    def __init__(self, device):
        self.device = device

    def enter(self):
        pass

    def exec(self):
        pass

    def leave(self):
        pass
