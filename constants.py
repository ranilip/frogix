"""
Усі магічні числа і рядки проекту в одному місці.
Так їх легше знаходити і міняти при portуванні на інші плати (ESP32, Pico W).
"""

APP_VERSION = "v1.0.0"


NP_PIN  = 18    # NeoPixel WS2812 data line
BTN_PIN = 20    # Tactile push button
DHT_PIN = 27    # DHT11 data line


SHORT_PRESS_DURATION  = 3   # секунди -- поріг для Configuration AP
WIFI_PRESS_DURATION   = 8   # секунди -- поріг для ConfigurationWiFi (LiveServer)
LONG_PRESS_DURATION   = 13  # секунди -- поріг для FactoryReset
STUCK_BUTTON_DURATION = 60  # секунди -- кнопка вважається залиплою; ігноруємо


DHT_TEMP_MIN  = -10
DHT_TEMP_MAX  = 60
DHT_HUM_MIN   = 0
DHT_HUM_MAX   = 100
DHT_RETRY_COUNT = 3
DHT_RETRY_DELAY = 1   # секунд між спробами


RTC_I2C_ID = 1
RTC_SDA_PIN = 2
RTC_SCL_PIN = 3
RTC_DS3231_ADDR = 0x68
VALID_TIME_YEAR_MIN = 2024


LOCAL_INTERVAL_S = 15 * 60
UNSENT_HISTORY_POINTS = 288
DASHBOARD_HISTORY_POINTS = 96
DASHBOARD_INTERVAL_S = LOCAL_INTERVAL_S    # old default alias для сумісності


MQTT_INTERVAL_MIN_S  = 60          # 1 хвилина
MQTT_INTERVAL_MAX_S  = 12 * 3600   # 12 годин = 43200 с
MQTT_INTERVAL_STEP_S = 60          # крок 1 хвилина
MQTT_INTERVAL_DEFAULT_S = 5 * 60   # default 5 хвилин


WIFI_CONNECTION_TIMEOUT = 15


DEVICE_ID = "thsensor_dev"
MQTT_CLIENT_ID = DEVICE_ID  # backward-compatible alias

MQTT_DEFAULT_DEPARTMENT = "kpi"
MQTT_DEFAULT_ROOM = "kronos"

MQTT_KEEPALIVE  = 60


USE_DEEP_SLEEP = False

SLEEP_CPU_FREQ = 125 * 1_000_000


AP_SSID     = "thsensor"
AP_PASSWORD = "thsensor"   # мін 8 символів -- обмеження WPA2

AP_IP_ADDRESS = "192.168.4.1"


SESSION_TTL_S      = 30 * 60   # тривалість сесії після login (секунди)
MIN_PW_LENGTH      = 8         # мінімальна довжина пароля

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_S    = 60        # 1 хвилина блокування


IDLE_TIMEOUT_S = 5 * 60   # 5 хвилин


OTA_WINDOW_S = 3
OTA_POLL_MS  = 100   # частота check_msg() -- 100 мс достатньо швидко


SETTINGS_FILE     = 'settings.json'
MEASUREMENTS_FILE = 'measurements.jsonl'   # NDJSON: один JSON-обʼєкт на рядок
UNSENT_FILE       = 'unsent.jsonl'         # NDJSON: черга на MQTT публікацію


class TempUnit:
    METRIC:   str = "metric"      # Цельсій
    IMPERIAL: str = "imperial"    # Фаренгейт
    STANDARD: str = "standard"    # Кельвін


METRIC_UNITS = {
    "temperature": None,    # вирішується runtime з settings.units
    "humidity":    "%",
    "pressure":    "hPa",
    "co2":         "ppm",
    "voc":         "ppb",
    "lux":         "lx",
}


class Color:
    OFF:     tuple = (0, 0, 0)
    RED:     tuple = (64, 0, 0)
    ORANGE:  tuple = (64, 22, 0)
    YELLOW:  tuple = (64, 49, 0)
    GREEN:   tuple = (6, 64, 0)
    TEAL:    tuple = (0, 64, 53)
    CYAN:    tuple = (0, 37, 64)
    BLUE:    tuple = (0, 15, 64)
    VIOLET:  tuple = (26, 4, 64)
    PINK:    tuple = (64, 0, 31)
    MAGENTA: tuple = PINK


LED_ROLE_DEFAULTS = {
    "alive":         {"color": "#1aff00", "brightness": 25},
    "measurement":   {"color": "#00ffd2", "brightness": 25},
    "config_ap":     {"color": "#0095ff", "brightness": 25},
    "config_sta":    {"color": "#003cff", "brightness": 25},
    "network":       {"color": "#6811ff", "brightness": 25},
    "error":         {"color": "#ff0000", "brightness": 25},
    "factory_reset": {"color": "#ff5900", "brightness": 25},
}
