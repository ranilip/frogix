"""
helpers.py -- допоміжні утиліти, які не належать до жодного конкретного стану
чи модуля. Сюди вставляємо речі типу читання/запису settings.json,
форматування часу.
"""

import binascii
import hashlib
import json
import os
import time

from constants import (
    SETTINGS_FILE, MEASUREMENTS_FILE, UNSENT_FILE,
    DASHBOARD_HISTORY_POINTS, LOCAL_INTERVAL_S,
    UNSENT_HISTORY_POINTS, VALID_TIME_YEAR_MIN,
    RTC_I2C_ID, RTC_SDA_PIN, RTC_SCL_PIN, RTC_DS3231_ADDR,
    DEVICE_ID, MQTT_DEFAULT_DEPARTMENT, MQTT_DEFAULT_ROOM,
)
from models.settings import Settings



def save_settings(settings: Settings) -> None:
    """
    Зберігає Settings у settings.json **атомарно**.

    Принцип атомарного запису:
        1. Серіалізуємо в тимчасовий файл settings.json.tmp.
        2. Видаляємо старий settings.json (якщо є).
        3. Перейменовуємо .tmp у settings.json.

    Якщо живлення зникне посеред кроку 1 -- оригінал лишився цілий,
    .tmp буде проігнорований при наступному читанні.
    Якщо посеред кроку 3 (rename) -- це майже миттєва операція файлової
    системи, шанс її перерви мізерний.

    Без цього: запис безпосередньо в settings.json може залишити пів-файл
    при втраті живлення -- settings.json буде пошкоджений, при наступному
    boot читання впаде з JSONDecodeError, пристрій кине Error → reset →
    петля.
    """
    tmp_file = SETTINGS_FILE + '.tmp'

    with open(tmp_file, 'w') as f:
        json.dump(settings.model_dump(), f)

    try:
        os.remove(SETTINGS_FILE)
    except OSError:
        pass

    os.rename(tmp_file, SETTINGS_FILE)


def read_settings() -> Settings:
    """
    Читає settings.json і повертає Settings-обʼєкт.

    Якщо файл відсутній -- кидає OSError. Цю помилку ловить Init state
    і запускає Configuration mode (перший запуск пристрою -- налаштувань
    ще немає).

    Якщо файл існує, але містить невалідний JSON -- кидає ValueError.

    Міграції:
        Старе поле measurement_interval → нове mqtt_interval. Якщо у
        файлі є тільки старе ім'я, перейменовуємо в пам'яті і
        зберігаємо назад через save_settings -- наступні читання
        будуть без міграції.
    """
    with open(SETTINGS_FILE, 'r') as f:
        data = json.load(f)

    migrated = False
    if 'measurement_interval' in data:
        if 'mqtt_interval' not in data:
            data['mqtt_interval'] = data['measurement_interval']
        del data['measurement_interval']
        migrated = True

    settings = Settings(**data)

    if migrated:
        try:
            save_settings(settings)
            print("Settings migrated: measurement_interval → mqtt_interval")
        except Exception as e:
            print(f"Settings migration save failed: {e} (non-fatal)")

    return settings



def get_base_topic(settings: Settings) -> str:
    """
    MQTT base topic у форматі thsensor-main:
        {department}/{room}/thsensor/{DEVICE_ID}
    """
    department = getattr(settings, "department", None) or MQTT_DEFAULT_DEPARTMENT
    room = getattr(settings, "room", None) or MQTT_DEFAULT_ROOM
    return f"{department}/{room}/thsensor/{DEVICE_ID}"



def format_time(seconds: int) -> str:
    """
    Форматує інтервал у годинах/хвилинах/секундах.
    Використовується для відображення uptime у дашборді (етап 13).

    Приклад: 3725 → "1h 2m 5s"
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {minutes}m {secs}s"



def get_iso_timestamp() -> str:
    """
    Повертає поточний час у форматі ISO 8601 (UTC).
    Приклад: "2026-05-02T14:30:00Z"

    До синхронізації NTP (етап 7) MicroPython починає рахувати час
    з 1970-01-01 00:00:00 (epoch 0), тому timestamps будуть неправильні
    до першого підключення до мережі. Це нормально -- після першого
    NTP-sync усі наступні вимірювання будуть з правильним часом.
    """
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )


def is_time_valid() -> bool:
    """True when system time is plausible enough for wall-clock scheduling."""
    try:
        return time.localtime()[0] >= VALID_TIME_YEAR_MIN
    except Exception:
        return False


def seconds_until_next_measurement(interval_s: int) -> int:
    """
    Return seconds to the next wall-clock slot for interval_s.
    Example for 300s: :00, :05, :10, ...
    Falls back to interval_s when time is not valid.
    """
    if not is_time_valid():
        return interval_s
    try:
        t = time.localtime()
        seconds_today = t[3] * 3600 + t[4] * 60 + t[5]
        remainder = seconds_today % interval_s
        wait_s = interval_s - remainder
        return wait_s if wait_s > 0 else interval_s
    except Exception:
        return interval_s


def _bcd_to_int(value: int) -> int:
    return ((value >> 4) * 10) + (value & 0x0f)


def _int_to_bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _rtc_i2c():
    from machine import I2C, Pin
    return I2C(RTC_I2C_ID, sda=Pin(RTC_SDA_PIN), scl=Pin(RTC_SCL_PIN))


def sync_time_from_rtc() -> bool:
    """
    Best-effort DS3231 -> system RTC sync.
    Returns False if the module is absent or its time is not plausible.
    """
    try:
        i2c = _rtc_i2c()
        data = i2c.readfrom_mem(RTC_DS3231_ADDR, 0x00, 7)
        second = _bcd_to_int(data[0] & 0x7f)
        minute = _bcd_to_int(data[1] & 0x7f)
        hour = _bcd_to_int(data[2] & 0x3f)
        day = _bcd_to_int(data[4] & 0x3f)
        month = _bcd_to_int(data[5] & 0x1f)
        year = 2000 + _bcd_to_int(data[6])
        if year < VALID_TIME_YEAR_MIN:
            return False
        from machine import RTC
        RTC().datetime((year, month, day, 0, hour, minute, second, 0))
        print(f"RTC synced: {get_iso_timestamp()}")
        return True
    except Exception as e:
        print(f"RTC sync skipped: {e}")
        return False


def sync_rtc_from_system() -> bool:
    """Best-effort system RTC -> DS3231 sync after NTP corrected time."""
    if not is_time_valid():
        return False
    try:
        t = time.localtime()
        payload = bytes((
            _int_to_bcd(t[5]),
            _int_to_bcd(t[4]),
            _int_to_bcd(t[3]),
            _int_to_bcd((t[6] % 7) + 1),
            _int_to_bcd(t[2]),
            _int_to_bcd(t[1]),
            _int_to_bcd(t[0] - 2000),
        ))
        _rtc_i2c().writeto_mem(RTC_DS3231_ADDR, 0x00, payload)
        print("RTC updated from system time")
        return True
    except Exception as e:
        print(f"RTC update skipped: {e}")
        return False



def _parse_iso_timestamp(ts: str):
    """Мінімальний ISO parser без datetime, дружній до MicroPython."""
    try:
        if not ts or len(ts) < 19:
            return None
        return (
            int(ts[0:4]), int(ts[5:7]), int(ts[8:10]),
            int(ts[11:13]), int(ts[14:16]), int(ts[17:19]),
            0, 0,
        )
    except (ValueError, TypeError):
        return None


def _timestamp_seconds(ts: str):
    parsed = _parse_iso_timestamp(ts)
    if parsed is None:
        return None
    try:
        return time.mktime(parsed)
    except Exception:
        try:
            return time.mktime(parsed + (0,))
        except Exception:
            return None


def _append_jsonl_with_limit(filename: str, record: dict, limit: int) -> None:
    with open(filename, 'a') as f:
        f.write(json.dumps(record) + "\n")

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
        if len(lines) > limit:
            with open(filename, 'w') as f:
                for line in lines[-limit:]:
                    f.write(line)
    except OSError:
        pass


def append_measurement(device, record: dict) -> None:
    """
    Додає рядок у measurements.jsonl не частіше ніж раз на 15 хвилин.
    Файл тримає максимум 96 точок для локального дашборду.

    Формат: NDJSON -- один JSON-обʼєкт на рядок.
    Приклад: {"ts":"2026-05-02T14:30:00Z","temperature":22.5,"humidity":55.0}

    Перевага NDJSON над CSV: вільна схема. Сенсори можуть додавати/прибирати
    метрики без редагування формату. Старі рядки без нових ключів просто
    не показують їх -- це ок для дашборду.
    """
    rows = []
    try:
        with open(MEASUREMENTS_FILE, 'r') as f:
            rows = [line for line in f.readlines() if line.strip()]
    except OSError:
        pass

    if rows:
        try:
            last = json.loads(rows[-1])
        except ValueError:
            last = {}
        last_s = _timestamp_seconds(last.get("ts", ""))
        current_s = _timestamp_seconds(record.get("ts", ""))
        if last_s is not None and current_s is not None:
            if current_s - last_s < LOCAL_INTERVAL_S:
                return

    _append_jsonl_with_limit(MEASUREMENTS_FILE, record, DASHBOARD_HISTORY_POINTS)



def append_to_unsent(record: dict) -> None:
    """Додає рядок у unsent.jsonl як NDJSON.
    Черга обмежена останніми 288 невисланими 5-хвилинними точками.
    """
    _append_jsonl_with_limit(UNSENT_FILE, record, UNSENT_HISTORY_POINTS)


def read_unsent_rows() -> list:
    """
    Повертає список dict з unsent.jsonl.
    Пустий список якщо файл відсутній або порожній.
    """
    rows = []
    try:
        with open(UNSENT_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def clear_unsent() -> None:
    """
    Очищує unsent.jsonl (truncate до 0 байт).
    Викликається тільки після успішного MQTT publish.
    """
    try:
        open(UNSENT_FILE, 'w').close()
    except OSError:
        pass



def generate_salt() -> str:
    """
    Генерує випадкову 16-байтну сіль і повертає як hex-рядок (32 символи).
    os.urandom працює і в MicroPython, і в CPython.
    """
    return binascii.hexlify(os.urandom(16)).decode()


def hash_password(password: str, salt_hex: str) -> str:
    """
    SHA-256(salt || password) → hex-рядок (64 символи).

    Без stretching (PBKDF2/scrypt/argon2) -- на embedded занадто дорого,
    і AP доступний лише локально, тому brute-force ризик мінімальний.
    """
    salt = binascii.unhexlify(salt_hex)
    h = hashlib.sha256()
    h.update(salt + password.encode())
    return binascii.hexlify(h.digest()).decode()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    """Повертає True якщо введений пароль збігається зі збереженим хешем."""
    if not salt_hex or not expected_hash:
        return False
    return hash_password(password, salt_hex) == expected_hash



def read_measurement_history() -> list:
    """
    Читає measurements.jsonl і повертає список dict.
    Кожен dict -- це повний запис вимірювання з усіма метриками.

    Приклад:
        [
          {"ts": "...", "temperature": 22.5, "humidity": 55.0},
          {"ts": "...", "temperature": 22.6, "humidity": 55.1, "pressure": 1013},
        ]

    Записи можуть мати РІЗНІ метрики (наприклад, після додавання
    нового сенсора в середині історії). Це фіча NDJSON.
    """
    rows = []
    try:
        with open(MEASUREMENTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows
