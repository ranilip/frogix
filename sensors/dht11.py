"""
sensors/dht11.py -- обгортка над DHT11 у формі Sensor.
"""

from machine import Pin
from dht import DHT11

from .base import Sensor


class DHT11Sensor(Sensor):
    name = "DHT11"
    metrics = ["temperature", "humidity"]

    def __init__(self, pin: int):
        self._pin_num = pin
        self._dht = None

    def setup(self) -> None:
        self._dht = DHT11(Pin(self._pin_num, Pin.IN))

    def read(self) -> dict:
        self._dht.measure()
        return {
            "temperature": self._dht.temperature(),
            "humidity": self._dht.humidity(),
        }
