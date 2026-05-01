"""
sensors/__init__.py -- реєстр активних сенсорів пристрою.

ЯК ДОДАТИ НОВИЙ СЕНСОР:
    1. Створити новий файл, наприклад sensors/bmp280.py:

           from .base import Sensor

           class BMP280Sensor(Sensor):
               name = "BMP280"
               metrics = ["pressure", "temperature_bmp"]

               def __init__(self, i2c_bus, address=0x76):
                   self._i2c = i2c_bus
                   self._addr = address

               def setup(self):
                   ...

               def read(self):
                   return {"pressure": ..., "temperature_bmp": ...}

    2. Якщо метрики ще не зареєстровані в METRIC_UNITS (constants.py) --
       додати їх туди ("pressure": "hPa" і т.д.).

    3. Імпортувати тут і додати в ALL.

    4. Все інше -- Diagnostics, Measurement, PublishData, дашборд --
       підхопить новий сенсор автоматично, нічого редагувати не треба.
"""

from .dht11 import DHT11Sensor
from constants import DHT_PIN


ALL = [
    DHT11Sensor(DHT_PIN),
]
