"""
boot.py -- виконується автоматично один раз при старті MicroPython,
ще до main.py. Сюди йде мінімальна системна ініціалізація:
тактова частота CPU, hostname для DHCP, тощо.
"""

import machine

machine.freq(125_000_000)

try:
    import network
    network.hostname("thsensor")
except (ImportError, AttributeError):
    pass
