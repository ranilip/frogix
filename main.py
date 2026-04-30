"""
main.py -- точка входу. MicroPython запускає його автоматично після boot.py.

Створює Device і запускає state machine. Уся реальна логіка -- у станах
в папці states/.
"""

from constants import APP_VERSION
from device import Device


def main() -> None:
    print(f"I am alive, app version {APP_VERSION}")
    Device().run()


if __name__ == '__main__':
    main()
