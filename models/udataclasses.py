"""
udataclasses.py -- мінімалістична реалізація dataclass для MicroPython.

Чому власна:
    CPython має модуль `dataclasses` зі стандартної бібліотеки, який
    автоматично будує `__init__`, `__repr__` та інші методи для класів,
    оголошених через `@dataclass`. У MicroPython цього модуля немає
    (надто великий для embedded). Тому ми пишемо мінімум, який нам
    потрібен.

Що підтримуємо:
    1. Декларативні поля з типами і дефолтами через анотації класу:
           class Foo(Dataclass):
               name: str = ""
               count: int = 0

    2. Декоратор @validator('field') для перевірки значень при присвоєнні:
           @validator('count')
           def check_count(self, value):
               if value < 0:
                   raise ValueError("count must be >= 0")

    3. Метод .model_dump() -- рекурсивна серіалізація в dict
       (для збереження як JSON).

    4. Автоматичне розгортання вкладених Dataclass з dict при конструюванні --
       це дозволяє напряму завантажити settings = Settings(**json_data),
       де json_data["wifi_settings"] -- це dict, а не WifiSettings-екземпляр.

Сумісність з MicroPython:
    MicroPython не гарантує створення __annotations__ для класів
    (на відміну від CPython). Тому поля виявляються через __init_subclass__,
    який сканує __dict__ підкласу в момент його визначення.
    Синтаксис `field: type = default` залишається -- він документує тип
    і працює в IDE, але ми не покладаємося на __annotations__ в рантаймі.
"""


class _ValidatorWrapper:
    """
    Обгортка над функцією-валідатором.

    MicroPython не дозволяє встановлювати довільні атрибути на об'єктах
    функцій (на відміну від CPython). Тому ми загортаємо функцію у клас:
    екземпляр класу -- звичайний Python-об'єкт, якому атрибути присвоювати
    можна. __call__ делегує виклик оригінальній функції.
    """
    def __init__(self, method, field_name):
        self._validates = field_name
        self._method = method

    def __call__(self, *args, **kwargs):
        return self._method(*args, **kwargs)


def validator(field_name):
    """
    Декоратор, який позначає метод як валідатор для конкретного поля.

    Сам по собі нічого не валідує -- лише ставить мітку на обгортці,
    щоб Dataclass.__init__ міг її знайти.

    Використання:
        class Settings(Dataclass):
            units: str = "metric"

            @validator('units')
            def check_units(self, value):
                if value not in ("metric", "imperial"):
                    raise ValueError(f"bad unit: {value}")
    """
    def decorator(method):
        return _ValidatorWrapper(method, field_name)
    return decorator


class Dataclass:
    """
    Базовий клас для декларативних моделей даних.

    Усі наші моделі (Settings, WifiSettings, MQTTSettings...) наслідуються
    від цього класу.
    """

    __fields__ = {}   # {field_name: default_value}
    __ftypes__ = {}   # {field_name: type} -- лише для Dataclass-полів

    @classmethod
    def _build_fields(cls):
        """
        Будує метадані полів для cls і кешує їх у cls.__fields__ / cls.__ftypes__.
        Викликається при першому __init__ кожного підкласу.

        Чому не __init_subclass__:
            У різних версіях MicroPython __init_subclass__ або не викликається
            автоматично, або вимагає @classmethod явно, або має інші
            несумісності. Ленива ініціалізація при першому __init__ надійніша.

        Виявлення полів:
            Скануємо cls.__dict__ (лише власні атрибути, без успадкованих).
            Поле -- це атрибут, який:
              • не починається з '_'
              • не є callable (метод, функція, _ValidatorWrapper)
              • не є classmethod / staticmethod / property
        """
        if '__fields__' in cls.__dict__:
            return  # вже побудовано для цього класу -- нічого не робимо

        ann = cls.__dict__.get('__annotations__', {})

        fields = {}  # {name: default_value}
        ftypes = {}  # {name: type}

        for k, v in cls.__dict__.items():
            if k.startswith('_'):
                continue
            if callable(v):
                continue
            if isinstance(v, (classmethod, staticmethod, property)):
                continue
            fields[k] = v
            if k in ann:
                ftypes[k] = ann[k]
            elif isinstance(v, Dataclass):
                ftypes[k] = type(v)

        cls.__fields__ = fields
        cls.__ftypes__ = ftypes

    def __init__(self, **kwargs):
        self.__class__._build_fields()

        validators = {}
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name)
            if hasattr(attr, '_validates'):
                validators[attr._validates] = attr

        object.__setattr__(self, '_validators', validators)

        for field_name, default in self.__class__.__fields__.items():
            if isinstance(default, Dataclass):
                default = type(default)(**default.model_dump())

            object.__setattr__(self, field_name, default)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
            return

        ftypes = self.__class__.__ftypes__
        if name in ftypes:
            field_type = ftypes[name]
            if isinstance(value, dict) and issubclass(field_type, Dataclass):
                value = field_type(**value)

        validators = self._validators
        if name in validators:
            validators[name](self, value)

        object.__setattr__(self, name, value)

    def model_dump(self):
        """
        Перетворює обʼєкт на dict, рекурсивно для вкладених Dataclass.
        Результат -- JSON-серіалізована структура.
        """
        result = {}
        for field_name in self.__class__.__fields__:
            value = getattr(self, field_name)
            if isinstance(value, Dataclass):
                result[field_name] = value.model_dump()
            else:
                result[field_name] = value
        return result

    def __repr__(self):
        items = []
        for f in self.__class__.__fields__:
            items.append(f"{f}={getattr(self, f)!r}")
        return f"{self.__class__.__name__}({', '.join(items)})"
