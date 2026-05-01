"""
sleep.py -- стан низького споживання між циклами вимірювання.

Завдання:
    1. Чисто завершити мережеві з'єднання:
         - опублікувати offline status у MQTT (з retain=True)
         - відключити MQTT клієнта
         - відключити Wi-Fi
    2. Знизити частоту CPU (light sleep) або повністю вимкнути CPU (deep sleep).
    3. Чекати до найближчої події:
         - локальний dashboard slot кожні LOCAL_INTERVAL_S (15 хв)
         - MQTT due time після mqtt_interval від останньої спроби
       У light sleep режимі -- поллимо кнопку, щоб користувач міг
       прокинути пристрій раніше (натиск 3-8с → AP, 8-13с → WiFi mode,
       13-60с → FactoryReset).
    4. Прокинутись:
         - light sleep → передаємо управління назад в Init для нового циклу
           (Init сам розбереться що робити, дивлячись на кнопку)
         - deep sleep → CPU перезавантажується, main.py стартує знову з нуля

Енергетика (orientовно для Pico 2 W):
    Light sleep @ 125 MHz, Wi-Fi off: ~30 mA
    Deep sleep:                        ~1 mA

Wake-on-button у deep sleep:
    На RP2040 (Pico W) deep sleep будиться лише таймером -- кнопка
    не може його перервати. На RP2350 (Pico 2 W) є wake-on-pin через
    machine.lightsleep(wake=...). Поки що `USE_DEEP_SLEEP=False` за
    замовчуванням, тому весь UX побудований на light sleep + поллінг.
    Якщо колись захочеться deep sleep на 2 W -- додати окрему гілку.
"""

import json
import time
import machine

from .state import AbstractState
from constants import (
    USE_DEEP_SLEEP, SLEEP_CPU_FREQ,
    LOCAL_INTERVAL_S,
)
from helpers import get_base_topic, is_time_valid, seconds_until_next_measurement


class Sleep(AbstractState):

    def enter(self):
        print(">> Sleep State")
        if self.device.last_wifi_status == 'fail':
            for _ in range(3):
                self.device.set_led("error")
                time.sleep_ms(150)
                self.device.led_off()
                time.sleep_ms(150)

        self.device.led_off()

    def exec(self):
        self._disconnect_mqtt()

        self._disconnect_wifi()

        configured_mqtt_interval_s = self.device.settings.mqtt_interval
        local_delay_s = seconds_until_next_measurement(LOCAL_INTERVAL_S)
        mqtt_delay_s = self._seconds_until_mqtt_due(configured_mqtt_interval_s)
        interval_s = max(1, min(local_delay_s, mqtt_delay_s))
        schedule_mode = "next local/MQTT due" if is_time_valid() else "fallback interval"

        if USE_DEEP_SLEEP:
            print(f"Entering deep sleep for {interval_s}s ({schedule_mode})...")
            machine.deepsleep(interval_s * 1000)
        else:
            print(
                f"Sleeping for {interval_s}s ({schedule_mode}, "
                f"light sleep @ {SLEEP_CPU_FREQ // 1_000_000} MHz)"
            )
            try:
                machine.freq(SLEEP_CPU_FREQ)
            except Exception:
                pass

            wake_reason = self._interruptible_sleep(interval_s)

            try:
                machine.freq(125_000_000)
            except Exception:
                pass

            if wake_reason == 'button':
                print("Button press detected during sleep -- early wake")

            from .init import Init
            self.device.change_state(Init(self.device))

    def leave(self):
        pass


    def _disconnect_mqtt(self) -> None:
        """
        Gracefully опублікувати offline статус і закрити MQTT клієнта.
        Якщо клієнта немає -- нічого не робимо.

        Чому два sleep_ms:
            client.publish() кладе payload у TCP-буфер, але не чекає
            доставки. Якщо одразу після publish викликати wlan.active(False)
            (це робить _disconnect_wifi далі), CYW43 драйвер не встигає
            відіслати буферизовані пакети -- виходить retransmit-цикл,
            STALL(0;...): timeout, send_ethernet failed: -110 спам у логах.
            300мс достатньо щоб TCP виштовхнув publish payload до broker'а,
            ще 200мс -- щоб FIN-handshake завершився після disconnect.
            Сумарно 500мс затримки vs 5-10с retry-спаму -- net economy
            активного часу радіо.
        """
        client = self.device.mqtt_client
        if client is None:
            return

        topic_status = f"{get_base_topic(self.device.settings)}/status"
        offline_payload = json.dumps({"status": "offline"})

        try:
            client.publish(topic_status, offline_payload, retain=True, qos=0)
            time.sleep_ms(300)   # TCP flush для publish payload
            client.disconnect()
            time.sleep_ms(200)   # FIN-handshake
            print("MQTT disconnected")
        except Exception as e:
            print(f"MQTT disconnect error: {e} (ignored)")

        self.device.mqtt_client = None

    def _disconnect_wifi(self) -> None:
        """Відключаємо STA, якщо було підключено."""
        wlan = self.device.wlan
        try:
            if wlan.isconnected():
                wlan.disconnect()
                time.sleep_ms(300)
            wlan.active(False)
            time.sleep_ms(500)
        except Exception as e:
            print(f"Wi-Fi disconnect error: {e} (ignored)")

    def _interruptible_sleep(self, total_seconds: int) -> str:
        """
        Sleep на total_seconds секунд із поллінгом кнопки кожні 100мс.

        Повертає:
            'button' -- користувач натиснув BTN_PIN (button.value() == 0)
                       у будь-який момент під час sleep
            'timer'  -- total_seconds минули без натиску

        Чому 100мс:
            Достатньо швидко для перцептивно-миттєвої реакції на натиск
            (max latency ~100мс), достатньо повільно щоб не жерти CPU
            cycles. У light sleep CPU й так простоює -- додатки
            від поллінгу не помітні.

        Energy:
            time.sleep_ms(100) у MicroPython використовує WFI / wait
            на нижньому рівні -- CPU реально простоює, не молотить busy-loop.
            Енергетика практично ідентична `time.sleep(N)`.
        """
        deadline = time.time() + total_seconds
        while time.time() < deadline:
            if self.device.button.value() == 0:
                return 'button'
            time.sleep_ms(100)
        return 'timer'

    def _seconds_until_mqtt_due(self, interval_s: int) -> int:
        """Seconds until mqtt_interval has elapsed since last MQTT attempt."""
        last = getattr(self.device, 'last_mqtt_attempt_at', 0)
        if last == 0:
            return interval_s
        due_at = last + interval_s
        return max(1, int(due_at - time.time()))
