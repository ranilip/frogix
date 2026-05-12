"""
connecting_network.py -- підключення до Wi-Fi + NTP + MQTT broker.

Завдання:
    1. Активувати STA інтерфейс і з'єднатись з Wi-Fi за credentials.
    2. Якщо Wi-Fi є -- синхронізувати час через NTP (non-fatal).
    3. Якщо Wi-Fi є -- підключитись до MQTT broker:
         - встановити LWT (Last Will and Testament -- broker сам опублікує
           "offline" статус коли пристрій раптово відключиться)
         - опублікувати "online" повідомлення з retain=True
    4. Перейти в PublishData (реальна публікація даних).

Гілки помилок (всі НЕ призводять до reset -- реселф-loop при offline був би
шкідливим):
    - SSID порожній або Wi-Fi connect timeout → пропускаємо публікацію,
      йдемо одразу у Sleep. Дані вже в unsent.jsonl на flash, наступний
      цикл спробує ще раз. Так уникаємо reset-loop при тимчасовій
      проблемі з мережею.
    - MQTT connect не вдалось → mqtt_client лишається None →
      PublishData пропускає публікацію → дані лишаються в unsent.jsonl.
"""

import json
import time

from .state import AbstractState
from .publish_data import PublishData
from .sleep import Sleep
from constants import (
    WIFI_CONNECTION_TIMEOUT,
    DEVICE_ID, MQTT_KEEPALIVE,
)
from helpers import get_base_topic, get_iso_timestamp, sync_rtc_from_system


class ConnectingNetwork(AbstractState):

    def enter(self):
        print(">> ConnectingNetwork State")
        self.device.set_led("network")

    def exec(self):
        if not self._connect_wifi():
            print("Skipping publish (no network), going to Sleep")
            self.device.change_state(Sleep(self.device))
            return
        self._sync_ntp()

        self._connect_mqtt()

        self.device.change_state(PublishData(self.device))

    def leave(self):
        self.device.led_off()


    def _status_name(self, status: int) -> str:
        import network
        if status == getattr(network, "STAT_GOT_IP", 3):
            return "STAT_GOT_IP"
        if status == getattr(network, "STAT_CONNECTING", 1):
            return "STAT_CONNECTING"
        if status == getattr(network, "STAT_IDLE", 0):
            return "STAT_IDLE"
        if status == getattr(network, "STAT_CONNECT_FAIL", -1):
            return "STAT_CONNECT_FAIL"
        if status == getattr(network, "STAT_NO_AP_FOUND", -2):
            return "STAT_NO_AP_FOUND"
        if status == getattr(network, "STAT_WRONG_PASSWORD", -3):
            return "STAT_WRONG_PASSWORD"
        return "UNKNOWN"

    def _connect_wifi(self) -> bool:
        settings = self.device.settings
        ssid = settings.wifi_settings.ssid
        password = settings.wifi_settings.password

        if not ssid:
            print("Wi-Fi SSID is empty -- skipping connection")
            self.device.last_wifi_status = 'no_credentials'
            return False

        wlan = self.device.wlan
        try:
            if wlan.active():
                try:
                    wlan.disconnect()
                except Exception:
                    pass
                wlan.active(False)
                time.sleep_ms(300)
        except Exception:
            pass
        wlan.active(True)
        time.sleep_ms(300)

        if wlan.isconnected():
            print(f"Already connected. IP: {wlan.ifconfig()[0]}")
            self.device.last_wifi_status = 'ok'
            return True

        print(f"Connecting to '{ssid}'...")
        wlan.connect(ssid, password)

        timeout = WIFI_CONNECTION_TIMEOUT
        while timeout > 0:
            status = wlan.status()
            if status >= 3 or status < 0:
                break
            time.sleep(1)
            timeout -= 1
            print(".", end="")
        print()

        status = wlan.status()
        if status != 3:
            print(f"Wi-Fi connection failed: status={status} ({self._status_name(status)})")
            self.device.last_wifi_status = 'fail'
            return False

        print(f"Connected. IP: {wlan.ifconfig()[0]}")
        self.device.last_wifi_status = 'ok'
        return True

    def _sync_ntp(self) -> None:
        import ntptime
        ntp_host = self.device.settings.ntp_server
        try:
            ntptime.host = ntp_host
            ntptime.settime()
            print(f"NTP synced via {ntp_host}: {get_iso_timestamp()}")
            sync_rtc_from_system()
        except Exception as e:
            print(f"NTP sync failed via {ntp_host}: {e} (non-fatal)")

    def _connect_mqtt(self) -> bool:
        """
        Підключається до MQTT broker, реєструє LWT, публікує online status.
        При успіху self.device.mqtt_client встановлюється на робочого клієнта.
        """
        from umqtt.simple import MQTTClient

        mqtt_settings = self.device.settings.mqtt_settings
        if not mqtt_settings.server:
            print("MQTT server not configured -- skipping")
            self.device.last_mqtt_status = 'no_credentials'
            return False

        topic_status = f"{get_base_topic(self.device.settings)}/status"
        user = mqtt_settings.user or None
        password = mqtt_settings.password if user is not None else None

        client = MQTTClient(
            client_id=DEVICE_ID,
            server=mqtt_settings.server,
            port=mqtt_settings.port,
            user=user,
            password=password,
            keepalive=MQTT_KEEPALIVE,
            ssl=getattr(mqtt_settings, "ssl", False),
        )

        offline_payload = json.dumps({"status": "offline", "lwt": True})
        client.set_last_will(topic_status, offline_payload, retain=True, qos=0)

        online_payload = json.dumps({"status": "online"})

        try:
            client.connect()
            client.publish(topic_status, online_payload, retain=True, qos=0)

        except Exception as e:
            print(f"MQTT setup failed: {e}")
            self.device.last_mqtt_status = 'fail'
            return False

        self.device.mqtt_client = client
        self.device.last_mqtt_status = 'ok'
        print(f"MQTT connected to {mqtt_settings.server}:{mqtt_settings.port}")
        return True
