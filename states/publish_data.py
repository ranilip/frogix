"""
publish_data.py -- публікація накопичених вимірювань у MQTT.

Завдання:
    1. Якщо MQTT не підключений → пропустити (дані залишаться в unsent.jsonl).
    2. Прочитати unsent.jsonl (список dict з усіма метриками).
    3. Скласти JSON payload -- список metrics, де кожен елемент описує
       одну метрику одного timestamp.
    4. Опублікувати на /data топік.
    5. ЯКЩО publish зайшов → очистити unsent.jsonl. Інакше -- лишити
       (наступний MQTT slot, при відновленні broker'а, відправить весь
       накопичений залишок).

    last_mqtt_attempt_at оновлюється у Measurement state ДО ConnectingNetwork,
    тому тут нічого додатково не зберігаємо.
"""

import json

from .state import AbstractState
from .ota import OTA
from constants import METRIC_UNITS
from helpers import get_base_topic, get_iso_timestamp, read_unsent_rows, clear_unsent


class PublishData(AbstractState):

    def enter(self):
        print(">> PublishData State")
        self.device.set_led("network")

    def exec(self):
        if self.device.mqtt_client is None:
            print("MQTT not connected -- skipping publish (data stays in unsent.jsonl)")
            self.device.change_state(OTA(self.device))
            return

        rows = read_unsent_rows()
        if not rows:
            print("No data to publish (unsent.jsonl empty)")
            self.device.change_state(OTA(self.device))
            return

        temp_unit = self.device.settings.units
        payload = {
            "dt": get_iso_timestamp(),
            "metrics": [],
        }

        for record in rows:
            ts = record.get("ts", "")
            for key, value in record.items():
                if key == "ts":
                    continue
                payload["metrics"].append({
                    "dt": ts,
                    "name": key,
                    "value": value,
                    "units": self._unit_for(key, temp_unit),
                })

        topic = f"{get_base_topic(self.device.settings)}/data"
        try:
            self.device.mqtt_client.publish(
                topic, json.dumps(payload), retain=False, qos=1
            )
            print(f"Published {len(rows)} measurement(s), {len(payload['metrics'])} metric(s)")
            clear_unsent()
            print("unsent.jsonl cleared")
        except Exception as e:
            print(f"MQTT publish failed: {e} -- keeping unsent.jsonl for retry")

        self.device.change_state(OTA(self.device))

    def _unit_for(self, metric_name: str, temp_unit: str) -> str:
        """Повертає одиницю для метрики з METRIC_UNITS, з fallback."""
        unit = METRIC_UNITS.get(metric_name, "")
        if unit is None:
            return temp_unit
        return unit

    def leave(self):
        self.device.led_off()
