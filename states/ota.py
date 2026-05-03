"""
ota.py -- Over-The-Air оновлення налаштувань через MQTT.

Workflow:
    1. Підписуємось на топік {base}/{client_id}/settings.
    2. Реєструємо callback, який обробляє вхідні retained повідомлення.
    3. Кілька секунд (OTA_WINDOW_S) поллємо check_msg() -- broker за цей
       час встигає віддати найсвіжіше retained повідомлення.
    4. Йдемо в Sleep.

Що відбувається у callback:
    Парсимо JSON. Пробуємо застосувати кожен ключ через Settings dataclass --
    validators ловлять невалідне (наприклад, interval=5 буде reject-нуто).
    Якщо хоч один ключ валідний -- save_settings().
    Зміни вступають у силу з наступного циклу (наприклад, новий
    mqtt_interval буде використаний у Sleep вже зараз).
"""

import json
import time

from .state import AbstractState
from .sleep import Sleep
from constants import OTA_WINDOW_S, OTA_POLL_MS
from helpers import get_base_topic, save_settings


class OTA(AbstractState):

    def enter(self):
        print(">> OTA State")
        self.device.set_led("network")

    def exec(self):
        client = self.device.mqtt_client
        if client is None:
            self.device.change_state(Sleep(self.device))
            return

        base_topic = get_base_topic(self.device.settings)
        topic_settings = f"{base_topic}/settings"
        topic_command = f"{base_topic}/command"

        def on_msg(topic, payload):
            try:
                topic_str = topic.decode() if isinstance(topic, bytes) else topic
                payload_str = payload.decode() if isinstance(payload, bytes) else payload
                if topic_str != topic_settings:
                    return
                self._apply_settings(payload_str)
            except Exception as e:
                print(f"OTA callback error: {e}")

        try:
            client.set_callback(on_msg)
            client.subscribe(topic_settings)
            client.subscribe(topic_command)
        except Exception as e:
            print(f"OTA subscribe failed: {e}")
            self.device.change_state(Sleep(self.device))
            return

        deadline = time.time() + OTA_WINDOW_S
        while time.time() < deadline:
            try:
                client.check_msg()
            except Exception as e:
                print(f"OTA check_msg error: {e}")
                break
            time.sleep_ms(OTA_POLL_MS)

        self.device.change_state(Sleep(self.device))

    def _apply_settings(self, payload_str: str) -> None:
        """
        Парсить JSON, валідує через Settings dataclass, зберігає.
        """
        try:
            data = json.loads(payload_str)
        except ValueError as e:
            print(f"OTA invalid JSON: {e}")
            return

        if not isinstance(data, dict):
            print(f"OTA payload not an object: {type(data).__name__}")
            return

        applied = []
        rejected = []

        for key, value in data.items():
            if not hasattr(self.device.settings, key):
                rejected.append((key, "unknown field"))
                continue
            try:
                setattr(self.device.settings, key, value)
                applied.append(key)
            except (ValueError, TypeError) as e:
                rejected.append((key, str(e)))

        if applied:
            save_settings(self.device.settings)
            print(f"OTA applied: {applied}")
        if rejected:
            print(f"OTA rejected: {rejected}")

    def leave(self):
        self.device.led_off()
