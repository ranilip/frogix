"""
settings.py -- структура settings.json.

Описує всі параметри, які пристрій зберігає на flash між reboot:
Wi-Fi credentials, MQTT broker, NTP, інтервал вимірювань, hash пароля до
веб-інтерфейсу.
"""

from .udataclasses import Dataclass, validator
from constants import (
    TempUnit,
    MQTT_INTERVAL_MIN_S, MQTT_INTERVAL_MAX_S, MQTT_INTERVAL_STEP_S,
    MQTT_INTERVAL_DEFAULT_S,
    LED_ROLE_DEFAULTS, AP_SSID, AP_PASSWORD,
    MQTT_DEFAULT_DEPARTMENT, MQTT_DEFAULT_ROOM,
)



class WifiSettings(Dataclass):
    """Параметри підключення до домашнього Wi-Fi (STA mode)."""
    ssid: str = ""
    password: str = ""


class AccessPointSettings(Dataclass):
    """Параметри Configuration Access Point."""
    ssid: str = AP_SSID
    password: str = AP_PASSWORD

    @validator('ssid')
    def check_ssid(self, value):
        if not isinstance(value, str):
            raise ValueError("AP SSID must be a string")
        if not value.strip():
            raise ValueError("AP SSID is required")
        if len(value) > 32:
            raise ValueError("AP SSID must be 32 characters or less")

    @validator('password')
    def check_password(self, value):
        if not isinstance(value, str):
            raise ValueError("AP password must be a string")
        if len(value) < 8:
            raise ValueError("AP password must be at least 8 characters")
        if len(value) > 63:
            raise ValueError("AP password must be 63 characters or less")


class MQTTSettings(Dataclass):
    """Параметри підключення до MQTT broker."""
    server: str = ""
    port: int = 1883
    user: str = ""
    password: str = ""
    ssl: bool = False
    cert: str = ""


class ConfigurationAuth(Dataclass):
    """
    Зберігає hash пароля до веб-інтерфейсу.

    Сам пароль НЕ зберігається -- тільки SHA-256 hash з 16-байтовою сіллю.
    Деталі генерації -- в етапі 11 (авторизація).
    """
    salt: str = ""           # hex-рядок, 32 символи (16 байт)
    password_hash: str = ""  # hex-рядок, 64 символи (32 байти)


class LedRole(Dataclass):
    """Колір і яскравість одного LED-стану."""
    color: str = "#ffffff"
    brightness: int = 25

    @validator('color')
    def check_color(self, value):
        if not isinstance(value, str):
            raise ValueError("LED color must be a string")
        if len(value) != 7 or value[0] != "#":
            raise ValueError("LED color must use #RRGGBB format")
        try:
            int(value[1:], 16)
        except ValueError:
            raise ValueError("LED color must use #RRGGBB format")

    @validator('brightness')
    def check_brightness(self, value):
        if not isinstance(value, int):
            raise ValueError("LED brightness must be int")
        if value < 0 or value > 100:
            raise ValueError("LED brightness must be between 0 and 100")


class LedSettings(Dataclass):
    """Налаштування NeoPixel для основних режимів пристрою."""
    alive: LedRole = LedRole(**LED_ROLE_DEFAULTS["alive"])
    measurement: LedRole = LedRole(**LED_ROLE_DEFAULTS["measurement"])
    config_ap: LedRole = LedRole(**LED_ROLE_DEFAULTS["config_ap"])
    config_sta: LedRole = LedRole(**LED_ROLE_DEFAULTS["config_sta"])
    network: LedRole = LedRole(**LED_ROLE_DEFAULTS["network"])
    error: LedRole = LedRole(**LED_ROLE_DEFAULTS["error"])
    factory_reset: LedRole = LedRole(**LED_ROLE_DEFAULTS["factory_reset"])

    def validate_unique_colors(self):
        seen = {}
        for role in self.__class__.__fields__:
            color = getattr(self, role).color.lower()
            if color in seen:
                raise ValueError(
                    f"LED colors must be unique: {seen[color]} and {role} both use {color}"
                )
            seen[color] = role



class Settings(Dataclass):
    """
    Усі налаштування пристрою. Зберігається в settings.json.

    Дефолтні значення відповідають "першому запуску" -- пристрій
    у Configuration mode чекає на введення Wi-Fi і MQTT.

    `mqtt_interval` -- як часто пристрій публікує накопичені виміри
    у MQTT broker (1хв-12год, step 1хв). Локальний dashboard
    пишеться окремо раз на 15 хвилин.
    """
    units: str = TempUnit.METRIC
    department: str = MQTT_DEFAULT_DEPARTMENT
    room: str = MQTT_DEFAULT_ROOM
    mqtt_interval: int = MQTT_INTERVAL_DEFAULT_S
    ntp_server: str = "pool.ntp.org"
    wifi_settings: WifiSettings = WifiSettings()
    ap_settings: AccessPointSettings = AccessPointSettings()
    mqtt_settings: MQTTSettings = MQTTSettings()
    led_settings: LedSettings = LedSettings()
    configuration_auth: ConfigurationAuth = ConfigurationAuth()

    @validator('units')
    def check_units(self, value):
        valid = (TempUnit.METRIC, TempUnit.IMPERIAL, TempUnit.STANDARD)
        if value not in valid:
            raise ValueError(f"Unit '{value}' is invalid, must be one of {valid}")

    @validator('mqtt_interval')
    def check_mqtt_interval(self, value):
        if not isinstance(value, int):
            raise ValueError(f"Interval must be int, got {type(value).__name__}")
        if value < MQTT_INTERVAL_MIN_S:
            raise ValueError(
                f"Interval too short: {value}s (min {MQTT_INTERVAL_MIN_S}s = 1min)"
            )
        if value > MQTT_INTERVAL_MAX_S:
            raise ValueError(
                f"Interval too long: {value}s (max {MQTT_INTERVAL_MAX_S}s = 12h)"
            )
        if value % MQTT_INTERVAL_STEP_S != 0:
            raise ValueError(f"Interval must use {MQTT_INTERVAL_STEP_S}-second steps")

    @validator('led_settings')
    def check_led_settings(self, value):
        if hasattr(value, "validate_unique_colors"):
            value.validate_unique_colors()
