"""
sensors/base.py -- абстрактний клас для всіх сенсорів.

Кожен конкретний сенсор успадковується від Sensor і реалізує:
    - name (рядок) -- людинаське ім'я для логів
    - metrics (список) -- назви метрик, які цей сенсор продукує
    - setup() -- ініціалізація hardware (одноразово)
    - read() → dict -- фактичне читання, повертає {metric_name: value}

Архітектура дозволяє додавати нові сенсори без зміни Measurement,
PublishData чи дашборду -- достатньо створити новий клас і
зареєструвати його у sensors/__init__.py.
"""


class Sensor:
    name: str = "abstract"
    metrics: list = []

    def setup(self) -> None:
        """Ініціалізує hardware. Викликається один раз перед першим read()."""
        pass

    def read(self) -> dict:
        """
        Виконує фактичне зчитування з hardware.
        Повертає dict {metric_name: numeric_value}.
        Кидає Exception якщо сенсор не відповідає чи дає невалідні дані.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.read() not implemented")
