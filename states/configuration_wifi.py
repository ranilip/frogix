"""
configuration_wifi.py -- стан "дашборд через домашню Wi-Fi" (LiveServer).

Workflow:
    1. Вимикаємо AP (на випадок чистого входу), вимикаємо MQTT.
    2. Активуємо STA, конектимось до збереженої мережі.
    3. Якщо connect не вдався → fallback у звичайну Configuration (AP).
       Користувач не лишається без виходу -- він зможе перенастроїти
       Wi-Fi через AP-режим.
    4. Якщо connect ок → запускаємо Microdot HTTP-сервер на STA IP
       + idle_monitor + background measurement_task (як у Configuration).
    5. Опційно -- анонсуємо себе як thsensor.local через mDNS.
    6. Idle 5хв → AP off → STA off → Init для нового циклу.

Енергетика:
    STA up + Microdot listening: ~30-50 mA постійно. Активується ТІЛЬКИ
    коли користувач натиснув кнопку 8-13с -- тобто свідомо хоче дашборд
    через домашню мережу. Не включається автоматично.
"""

import time

import network

from .state import AbstractState
from constants import WIFI_CONNECTION_TIMEOUT


class ConfigurationWiFi(AbstractState):

    def enter(self):
        print(">> ConfigurationWiFi State")
        self.device.last_wifi_status = "unknown"
        self.device.last_mqtt_status = "off"
        self.device.set_led("config_sta")

        for sensor in self.device.sensors:
            try:
                sensor.setup()
            except Exception as e:
                print(f"Sensor {sensor.name} setup failed in ConfigurationWiFi: {e}")

    def exec(self):
        try:
            if self.device.mqtt_client is not None:
                self.device.mqtt_client.disconnect()
                self.device.mqtt_client = None
        except Exception:
            self.device.mqtt_client = None

        try:
            ap = network.WLAN(network.AP_IF)
            if ap.active():
                ap.active(False)
                time.sleep_ms(500)
        except Exception:
            pass

        if not self._connect_sta():
            print("STA connect failed -- fallback to Configuration (AP)")
            self.device.last_wifi_status = 'fail'
            from .configuration import Configuration
            self.device.change_state(Configuration(self.device))
            return

        sta_ip = self.device.wlan.ifconfig()[0]
        print(f"STA up. Dashboard at http://{sta_ip}/  (or http://thsensor.local/ if mDNS)")
        self.device.last_wifi_status = 'ok'

        self._run_microdot()

        try:
            self.device.wlan.disconnect()
            self.device.wlan.active(False)
        except Exception:
            pass

        from .init import Init
        self.device.change_state(Init(self.device))

    def leave(self):
        self.device.led_off()


    def _status_name(self, status: int) -> str:
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

    def _connect_sta(self) -> bool:
        """
        Підключається до домашньої Wi-Fi за credentials з settings.
        Повертає True/False.
        """
        settings = self.device.settings
        ssid = settings.wifi_settings.ssid
        password = settings.wifi_settings.password

        if not ssid:
            print("Wi-Fi SSID is empty -- cannot enter ConfigurationWiFi")
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
            wlan.active(True)
            time.sleep_ms(300)
        except Exception as e:
            print(f"STA activation failed: {e}")
            return False

        if wlan.isconnected():
            print(f"STA already connected. IP: {wlan.ifconfig()[0]}")
            return True

        print(f"Connecting STA to '{ssid}'...")
        try:
            wlan.connect(ssid, password)
        except Exception as e:
            print(f"STA connect call failed: {e}")
            return False

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
        print(f"STA status: {status} ({self._status_name(status)})")
        return status == getattr(network, "STAT_GOT_IP", 3)

    def _run_microdot(self) -> None:
        """
        Запускає Microdot + idle_monitor + measurement_task.

        Логіка ідентична Configuration.exec() (секція 4) -- той самий
        idle timeout, той самий background task. Тут НЕ дублюємо код:
        викликаємо спільну функцію через Configuration.
        """
        from .configuration import _run_interactive_app
        _run_interactive_app(self.device, indicator_role="config_sta")
