"""
measurement.py -- стан вимірювання.

Завдання:
    1. Прочитати ВСІ зареєстровані сенсори (device.sensors), зібрати
       значення в один dict.
    2. Завжди записати запис у measurements.jsonl (NDJSON, для дашборду).
       append_measurement сам debounce'ить до 15-хв резолюції.
    3. ЯКЩО настав MQTT slot (минув mqtt_interval з last_mqtt_attempt_at):
         - додати запис у unsent.jsonl
         - перейти у ConnectingNetwork → PublishData
       ІНАКШЕ:
         - не пишемо в unsent (broker буде отримати тільки 1 точку/інтервал)
         - переходимо одразу у Sleep (швидке прокидання без Wi-Fi)

Чому Measurement йде ПЕРЕД ConnectingNetwork:
    Сенсори читаються локально, не залежать від мережі. Якщо Wi-Fi
    зараз мертвий, дашборд-файл на flash оновився, дані не втрачені.

Розв'язка local vs MQTT:
    Локальний дашборд оновлюється КОЖЕН цикл вимірювання (з 15-хв
    debounce). MQTT публікація -- ЛИШЕ за mqtt_interval (default
    5хв, користувач може 1хв-12год). Це дозволяє користувачу мати
    щільний дашборд при рідкісних MQTT-публікаціях (наприклад, на
    батарейному пристрої з MQTT раз на годину).
"""

import time

from .state import AbstractState
from .connecting_network import ConnectingNetwork
from .sleep import Sleep
from helpers import get_iso_timestamp, append_measurement, append_to_unsent


class Measurement(AbstractState):

    def enter(self):
        print(">> Measurement State")
        self.device.set_led("measurement")

    def exec(self):
        readings = {}
        for sensor in self.device.sensors:
            try:
                readings.update(sensor.read())
            except Exception as e:
                print(f"Sensor {sensor.name} read failed: {e} (skipping)")

        if not readings:
            print("No sensor data this cycle")
            self.device.change_state(Sleep(self.device))
            return

        timestamp = get_iso_timestamp()
        record = {"ts": timestamp}
        record.update(readings)

        append_measurement(self.device, record)

        if self._is_mqtt_slot():
            self.device.last_mqtt_attempt_at = time.time()
            append_to_unsent(record)
            print(f"Logged + queued for MQTT: {record}")
            self.device.change_state(ConnectingNetwork(self.device))
        else:
            print(f"Logged (local only): {record}")
            self.device.change_state(Sleep(self.device))

    def _is_mqtt_slot(self) -> bool:
        """
        True якщо настав час публікувати на MQTT broker.

        Перший цикл після boot (last_mqtt_attempt_at == 0) завжди
        вважається MQTT slot'ом -- щоб broker одразу побачив пристрій
        онлайн із актуальним виміром.
        """
        last = getattr(self.device, 'last_mqtt_attempt_at', 0)
        if last == 0:
            return True
        interval = self.device.settings.mqtt_interval
        return time.time() >= last + interval

    def leave(self):
        self.device.led_off()
