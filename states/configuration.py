"""
configuration.py -- піднімає AP, запускає Microdot веб-сервер з idle timer.

Workflow:
    1. Деактивувати STA -- на CYW43439 одночасний AP+STA працює через
       time-division і призводить до випадкових disconnect-ів обох інтерфейсів.
       Розділений режим (тільки AP АБО тільки STA в один момент часу) --
       стабільний і відповідає підходу курсу cv2-7.
    2. Активувати AP "thsensor".
    3. Створити Microdot додаток.
    4. Зареєструвати before_request hook -- оновлює last_request_time.
    5. Запустити фоновий asyncio task -- кожні 10 секунд перевіряє idle:
         якщо last_request_time > IDLE_TIMEOUT_S -- викликає app.shutdown().
    6. app.run() блокує, поки idle task не зупинить його.
    7. Виходимо → AP вимикаємо → повертаємось у Init для нового циклу.

Idle timeout reset:
    Будь-який запит (від polling JS на дашборді, від користувача в setup)
    скидає таймер. Поки браузер відкритий і polling працює -- AP живе.
    Як тільки tab закритий -- polling зупиняється, через IDLE_TIMEOUT_S
    AP сама вимикається.

Background measurements:
    Поки користувач сидить у веб-інтерфейсі, асинхронна задача
    measurement_task() читає сенсори кожні min(15 хв, mqtt_interval) і пише
    у measurements.jsonl. У unsent.jsonl додає тільки коли настав
    mqtt_interval slot. MQTT-публікації не відбуваються (STA off у
    Configuration mode), але дані будуть надіслані при наступному
    робочому циклі -- PublishData вичитає весь накопичений unsent.jsonl.

Design rationale -- чому не hybrid AP+STA:
    CYW43439 (Wi-Fi радіо Pico 2 W) теоретично підтримує одночасну роботу
    AP+STA, але на практиці це викликає нестабільне з'єднання -- драйвер
    робить time-division між інтерфейсами, що призводить до періодичних
    disconnect-ів. Тому пристрій працює в одному з двох режимів за раз:
    "робочий цикл" (тільки STA, MQTT публікації) або "конфігурація"
    (тільки AP, веб-інтерфейс).
"""

import asyncio
import time

import network

from microdot import Microdot

from .state import AbstractState
from constants import (
    AP_SSID, AP_PASSWORD, AP_IP_ADDRESS, IDLE_TIMEOUT_S,
    LOCAL_INTERVAL_S, MQTT_INTERVAL_DEFAULT_S,
)
from web import server
from helpers import get_iso_timestamp, append_measurement, append_to_unsent


class Configuration(AbstractState):

    def enter(self):
        print(">> Configuration State")
        self.device.last_wifi_status = "off"
        self.device.last_mqtt_status = "off"
        self.device.set_led("config_ap")

        for sensor in self.device.sensors:
            try:
                sensor.setup()
            except Exception as e:
                print(f"Sensor {sensor.name} setup failed in Configuration: {e}")

    def exec(self):
        try:
            if self.device.mqtt_client is not None:
                self.device.mqtt_client.disconnect()
                self.device.mqtt_client = None
        except Exception:
            self.device.mqtt_client = None

        try:
            if self.device.wlan.active():
                self.device.wlan.disconnect()
                self.device.wlan.active(False)
        except Exception:
            pass

        ap_settings = getattr(self.device.settings, "ap_settings", None)
        ap_ssid = getattr(ap_settings, "ssid", AP_SSID) or AP_SSID
        ap_password = getattr(ap_settings, "password", AP_PASSWORD) or AP_PASSWORD
        self.device.active_ap_ssid = ap_ssid
        self.device.active_ap_password = ap_password

        ap = network.WLAN(network.AP_IF)
        try:
            ap.active(False)
            time.sleep_ms(300)
        except Exception:
            pass

        try:
            ap.ifconfig((AP_IP_ADDRESS, "255.255.255.0", AP_IP_ADDRESS, AP_IP_ADDRESS))
        except Exception:
            pass

        try:
            ap.config(
                essid=ap_ssid,
                password=ap_password,
                channel=6,
                authmode=network.AUTH_WPA_WPA2_PSK,
            )
        except Exception:
            ap.config(essid=ap_ssid, password=ap_password, channel=6)
        ap.active(True)
        for _ in range(20):
            if ap.active():
                break
            time.sleep_ms(100)
        print(f"AP '{ap_ssid}' active. Open http://{ap.ifconfig()[0]}")

        try:
            _run_interactive_app(self.device, indicator_role="config_ap")
        finally:
            ap.active(False)

        from .init import Init
        self.device.change_state(Init(self.device))

    def leave(self):
        self.device.led_off()



def _run_interactive_app(device, indicator_role):
    """
    Запускає Microdot HTTP-сервер з паралельними задачами:
      - idle_monitor: вимикає сервер після IDLE_TIMEOUT_S без HTTP-запитів
      - measurement_task: фонові виміри кожні min(15 хв, mqtt_interval)
                          (15хв, дашборд резолюція)

    Викликається І з Configuration (AP активний) І з ConfigurationWiFi
    (STA активний). Різниця тільки у тому, який інтерфейс зараз
    піднятий -- Microdot listen'ить на 0.0.0.0:80 і обслуговує запити
    з обох однаково.

    Параметри:
        device          -- обʼєкт Device (для led, sensors, settings)
        indicator_role -- LED role під час idle ("config_ap" або "config_sta"),
                         щоб після виміру поновити правильний стан
    """
    app = Microdot()

    last_request = [time.time()]

    @app.before_request
    async def update_idle(req):
        last_request[0] = time.time()

    server.setup_endpoints(app, device)

    async def idle_monitor():
        while True:
            await asyncio.sleep(10)
            idle_for = time.time() - last_request[0]
            if idle_for > IDLE_TIMEOUT_S:
                print(f"Idle for {idle_for:.0f}s -- shutting down web server")
                app.shutdown()
                return

    async def button_monitor():
        while True:
            await asyncio.sleep_ms(100)
            if device.button.value() == 0:
                print("Button press detected in web mode -- returning to Init")
                app.shutdown()
                return

    async def measurement_task():
        while True:
            mqtt_interval = getattr(getattr(device, "settings", None), "mqtt_interval", MQTT_INTERVAL_DEFAULT_S)
            await asyncio.sleep(min(LOCAL_INTERVAL_S, mqtt_interval))
            device.set_led("measurement")
            readings = {}
            for sensor in device.sensors:
                try:
                    readings.update(sensor.read())
                except Exception as e:
                    print(f"[bg] sensor {sensor.name} failed: {e}")
            if readings:
                record = {"ts": get_iso_timestamp()}
                record.update(readings)
                append_measurement(device, record)
                last = getattr(device, 'last_mqtt_attempt_at', 0)
                interval = getattr(getattr(device, "settings", None), "mqtt_interval", MQTT_INTERVAL_DEFAULT_S)
                if last == 0 or time.time() >= last + interval:
                    device.last_mqtt_attempt_at = time.time()
                    append_to_unsent(record)
                    print(f"[bg] Logged + queued: {record}")
                else:
                    print(f"[bg] Logged (local only): {record}")
            device.set_led(indicator_role)

    async def runner():
        idle_task = asyncio.create_task(idle_monitor())
        button_task = asyncio.create_task(button_monitor())
        measure_task = asyncio.create_task(measurement_task())
        try:
            await app.start_server(host="0.0.0.0", port=80)
        finally:
            idle_task.cancel()
            button_task.cancel()
            measure_task.cancel()

    try:
        asyncio.run(runner())
    except Exception as e:
        print(f"Web server stopped: {e}")
