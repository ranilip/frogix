"""
server.py -- HTTP endpoints дашборду пристрою.

Етап 11 додає авторизацію:
    Public:
        GET  /              -- HTML дашборд
        GET  /style.css     -- стилі
        GET  /api/dht       -- поточні значення сенсора
        GET  /api/sysinfo   -- uptime, version, IP
        GET  /login         -- форма логіну
        POST /api/login     -- обробка логіну
        GET  /register      -- форма реєстрації (тільки якщо ще не зареєстрований)
        POST /api/register  -- обробка реєстрації
        POST /api/logout    -- стирає сесію

    Захищені (потребують login):
        GET  /setup         -- placeholder для форми налаштувань (етап 12)

Сесії зберігаються в _sessions dict у RAM. Reboot/deep_sleep інвалідує
всі активні сесії.
"""

import os
import binascii
import time

from microdot import Microdot, send_file, Response, redirect

from constants import APP_VERSION, DEVICE_ID, MQTT_KEEPALIVE, SESSION_TTL_S, MIN_PW_LENGTH, LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_S
from helpers import (
    format_time, save_settings,
    generate_salt, hash_password, verify_password,
    read_measurement_history,
)
from models.settings import AccessPointSettings, LedRole, LedSettings


_sessions: dict = {}

_login_failures: int = 0
_login_locked_until: int = 0


def setup_endpoints(app: Microdot, device) -> None:


    def is_registered() -> bool:
        """Чи був раніше встановлений admin пароль."""
        auth = device.settings.configuration_auth
        return bool(auth.salt) and bool(auth.password_hash)

    def cleanup_sessions():
        """Видаляє прострочені сесії з _sessions."""
        now = int(time.time())
        for sid in list(_sessions.keys()):
            if _sessions[sid]["exp"] < now:
                _sessions.pop(sid, None)

    def current_ap_credentials():
        """AP credentials currently used by this live Configuration session."""
        return (
            getattr(device, "active_ap_ssid", None) or AccessPointSettings.ssid,
            getattr(device, "active_ap_password", None) or AccessPointSettings.password,
        )

    def test_mqtt_connection(server_addr, port, user, password, ssl):
        """Try a real MQTT CONNECT before accepting broker settings."""
        from umqtt.simple import MQTTClient

        if not getattr(device, "wlan", None) or not device.wlan.isconnected():
            return False, "Device is not connected to STA Wi-Fi, so MQTT cannot be checked now"

        client = MQTTClient(
            client_id=DEVICE_ID,
            server=server_addr,
            port=port,
            user=user or None,
            password=password if user else None,
            keepalive=MQTT_KEEPALIVE,
            ssl=ssl,
        )
        try:
            client.connect()
            client.disconnect()
            return True, "MQTT connected successfully"
        except Exception as e:
            try:
                if getattr(client, "sock", None):
                    client.sock.close()
            except Exception:
                pass
            return False, mqtt_error_message(e, server_addr, port, ssl)

    def mqtt_error_message(error, server_addr, port, ssl):
        """Convert low-level socket/MQTT errors into setup-friendly text."""
        text = str(error)
        code = getattr(error, "args", [None])[0] if getattr(error, "args", None) else None
        target = f"{server_addr}:{port}"

        if code == 113 or "EHOSTUNREACH" in text:
            return (
                f"MQTT broker is not reachable at {target}. "
                "Check that the device is connected to Wi-Fi with internet access, "
                "the server address is correct, and the network/firewall allows this port."
            )
        if code == 110 or "ETIMEDOUT" in text or "timed out" in text:
            return (
                f"MQTT broker did not respond at {target}. "
                "Check the server, port, and whether the broker is online."
            )
        if code in (-2, 202) or "EAI" in text or "getaddrinfo" in text:
            return (
                f"MQTT server name could not be resolved: {server_addr}. "
                "Check the server address or DNS/internet access."
            )
        if "MQTTException" in text or code in (1, 2, 3, 4, 5):
            if code == 4:
                return "MQTT login failed. Check username and password."
            if code == 5:
                return "MQTT login is not authorized for this broker."
            return f"MQTT broker rejected the connection at {target}."
        if ssl and port == 1883:
            return "MQTT SSL is enabled, but port 1883 is usually non-SSL. Try port 8883 or turn SSL off."
        if (not ssl) and port == 8883:
            return "MQTT port 8883 usually requires SSL. Turn SSL on or use port 1883."
        return f"MQTT broker could not be checked at {target}. Check server, port, SSL, and credentials."

    def is_logged_in(req) -> bool:
        cleanup_sessions()
        sid = req.cookies.get("sid")
        if not sid or sid not in _sessions:
            return False
        _sessions[sid]["exp"] = int(time.time()) + SESSION_TTL_S
        return True

    def new_sid() -> str:
        """24 випадкові байти у hex (48 символів)."""
        return binascii.hexlify(os.urandom(24)).decode()

    def set_password(password: str) -> None:
        """Генерує сіль, рахує хеш, зберігає у settings.json."""
        salt = generate_salt()
        pw_hash = hash_password(password, salt)
        device.settings.configuration_auth.salt = salt
        device.settings.configuration_auth.password_hash = pw_hash
        save_settings(device.settings)
        device.settings_missing = False

    def check_password(password: str) -> bool:
        auth = device.settings.configuration_auth
        return verify_password(password, auth.salt, auth.password_hash)

    def protect(handler):
        """
        Декоратор для захищених routes.
        - Якщо ще не зареєстрований -- на /register.
        - Якщо не залогінений -- на /login.
        - Інакше -- викликаємо handler.
        """
        def wrapped(req, *args, **kwargs):
            if not is_registered():
                return redirect("/register")
            if not is_logged_in(req):
                return redirect("/login")
            return handler(req, *args, **kwargs)
        return wrapped


    @app.route("/")
    def index(req):
        return send_file("static/index.html", content_type="text/html; charset=utf-8")

    @app.route("/base.css")
    def base_css(req):
        return send_file("static/base.css", content_type="text/css")

    @app.route("/dashboard.css")
    def dashboard_css(req):
        return send_file("static/dashboard.css", content_type="text/css")

    @app.route("/modal.css")
    def modal_css(req):
        return send_file("static/modal.css", content_type="text/css")

    @app.route("/forms.css")
    def forms_css(req):
        return send_file("static/forms.css", content_type="text/css")

    @app.route("/api/readings")
    def api_readings(req):
        """
        Поточні значення з УСІХ зареєстрованих сенсорів.
        Повертає {"readings": {metric: value, ...}, "units": ..., "errors": [...]}.
        Дашборд рендерить картки динамічно -- додавши новий сенсор
        у sensors/__init__.py, ти автоматично побачиш нову картку.
        """
        readings = {}
        errors = []
        for sensor in device.sensors:
            try:
                readings.update(sensor.read())
            except Exception as e:
                errors.append({"sensor": sensor.name, "error": str(e)})
        return {
            "readings": readings,
            "units": device.settings.units,
            "errors": errors,
        }

    @app.route("/api/history")
    def api_history(req):
        """
        Повертає масив вимірювань з measurements.csv (rolling 24h).
        Public -- це не чутливі дані, лише історія в публічно-доступній мережі.
        """
        return {
            "units": device.settings.units,
            "data": read_measurement_history(),
        }

    @app.route("/index.js")
    def index_js(req):
        return send_file("static/index.js", content_type="application/javascript")

    @app.route("/auth-common.js")
    def auth_common_js(req):
        return send_file("static/auth-common.js", content_type="application/javascript")

    @app.route("/theme.js")
    def theme_js(req):
        return send_file("static/theme.js", content_type="application/javascript")

    @app.route("/api/ping")
    def api_ping(req):
        """
        Keepalive endpoint. Frontend пінгує сюди кожні 30с поки таб
        відкритий. Будь-який HTTP-запит проходить через before_request
        у Configuration.exec(), який оновлює last_request_time → AP не
        падає по IDLE_TIMEOUT_S (5 хв).

        Без цього: дашборд робить fetch'и тільки на чвертях години
        (кожні 15хв), між ними 15-хв тиша, AP вмирає через 5хв.
        З цим: 30с пінг < 5хв timeout, AP живе доки таб відкритий.
        """
        return {"ok": True}

    @app.route("/api/sysinfo")
    def api_sysinfo(req):
        uptime_s = int(time.time() - device.boot_time)
        sta_connected = False
        sysinfo = {
            "version": APP_VERSION,
            "uptime": format_time(uptime_s),
            "ap_ip": "",
            "sta_ip": "",
            "wifi_ssid": getattr(device.settings.wifi_settings, "ssid", "") if device.settings else "",
            "wifi_status": getattr(device, "last_wifi_status", "unknown"),
            "mqtt_status": getattr(device, "last_mqtt_status", "unknown"),
        }
        try:
            import network
            ap = network.WLAN(network.AP_IF)
            if ap.active():
                sysinfo["ap_ip"] = ap.ifconfig()[0]
        except Exception:
            pass
        try:
            if device.wlan.active() and device.wlan.isconnected():
                sta_connected = True
                sysinfo["sta_ip"] = device.wlan.ifconfig()[0]
        except Exception:
            pass
        if sysinfo["ap_ip"] and not sta_connected:
            sysinfo["wifi_status"] = "off"
            sysinfo["mqtt_status"] = "off"
        return sysinfo


    @app.route("/register")
    def register_page(req):
        if is_registered():
            return redirect("/login")
        return send_file("static/register.html", content_type="text/html; charset=utf-8")

    @app.route("/api/register", methods=["POST"])
    def register_post(req):
        if is_registered():
            return redirect("/login")
        form = req.form or {}
        p1 = form.get("password", "")
        p2 = form.get("password2", "")
        if len(p1) < MIN_PW_LENGTH:
            return Response(f"Password must be at least {MIN_PW_LENGTH} characters", 400)
        if p1 != p2:
            return Response("Passwords do not match", 400)
        set_password(p1)
        return redirect("/login")

    @app.route("/login")
    def login_page(req):
        if not is_registered():
            return redirect("/register")
        return send_file("static/login.html", content_type="text/html; charset=utf-8")

    @app.route("/api/login", methods=["POST"])
    def login_post(req):
        global _login_failures, _login_locked_until
        if not is_registered():
            return redirect("/register")
        now = int(time.time())
        if now < _login_locked_until:
            remaining = _login_locked_until - now
            return Response(f"Too many failed attempts. Try again in {remaining}s.", 429)
        form = req.form or {}
        password = form.get("password", "")
        if not check_password(password):
            _login_failures += 1
            if _login_failures >= LOGIN_MAX_ATTEMPTS:
                _login_locked_until = now + LOGIN_LOCKOUT_S
                _login_failures = 0
                return Response(f"Too many failed attempts. Try again in {LOGIN_LOCKOUT_S}s.", 429)
            return Response("Invalid password", 401)
        _login_failures = 0
        _login_locked_until = 0
        sid = new_sid()
        _sessions[sid] = {"exp": now + SESSION_TTL_S}
        next_url = form.get("next", "/setup")
        resp = redirect(next_url)
        resp.set_cookie("sid", sid, http_only=True, max_age=SESSION_TTL_S, path="/")
        return resp

    @app.route("/api/logout", methods=["POST"])
    def logout_post(req):
        sid = req.cookies.get("sid")
        if sid:
            _sessions.pop(sid, None)
        resp = redirect("/")
        resp.delete_cookie("sid", path="/")
        return resp


    @app.route("/setup")
    @protect
    def setup_page(req):
        return send_file("static/setup.html", content_type="text/html; charset=utf-8")

    @app.route("/setup.js")
    @protect
    def setup_js(req):
        return send_file("static/setup.js", content_type="application/javascript")

    @app.route("/api/settings")
    @protect
    def get_settings(req):
        """
        Повертає поточні налаштування з замаскованими паролями.
        UI використовує це щоб попередньо заповнити форми.
        """
        d = device.settings.model_dump()
        if d.get("wifi_settings", {}).get("password"):
            d["wifi_settings"]["password"] = ""
        if d.get("ap_settings", {}).get("password"):
            d["ap_settings"]["password"] = ""
        if d.get("mqtt_settings", {}).get("password"):
            d["mqtt_settings"]["password"] = ""
        d.pop("configuration_auth", None)
        return d

    @app.route("/api/settings/wifi", methods=["POST"])
    @protect
    def save_wifi(req):
        data = req.json or {}
        ssid = data.get("ssid", "").strip()
        password = data.get("password", "")
        if not ssid:
            return Response("SSID is required", 400)
        device.settings.wifi_settings.ssid = ssid
        if password:
            device.settings.wifi_settings.password = password
        save_settings(device.settings)
        device.settings_missing = False
        return {"status": "ok", "message": "Wi-Fi saved (effective on next cycle)"}

    @app.route("/api/settings/ap", methods=["POST"])
    @protect
    def save_ap(req):
        data = req.json or {}
        ssid = data.get("ssid", "").strip()
        password = data.get("password", "")
        if not ssid:
            return Response("AP SSID is required", 400)
        current = getattr(device.settings, "ap_settings", AccessPointSettings())
        try:
            device.settings.ap_settings = AccessPointSettings(
                ssid=ssid,
                password=password or current.password,
            )
        except (ValueError, TypeError) as e:
            return Response(str(e), 400)
        save_settings(device.settings)
        device.settings_missing = False
        return {"status": "ok", "message": "Access Point saved (effective next AP cycle)"}

    @app.route("/api/settings/mqtt", methods=["POST"])
    @protect
    def save_mqtt(req):
        data = req.json or {}
        server_addr = data.get("server", "").strip()
        port = data.get("port", 1883)
        user = data.get("user", "")
        password = data.get("password", "")
        department = data.get("department", "").strip()
        room = data.get("room", "").strip()
        ssl = bool(data.get("ssl", False))
        if not server_addr:
            return Response("MQTT server is required", 400)
        try:
            port_int = int(port)
        except (ValueError, TypeError):
            return Response("Port must be integer", 400)
        if not department:
            return Response("Department is required", 400)
        if not room:
            return Response("Room is required", 400)
        current_mqtt = device.settings.mqtt_settings
        effective_password = password if password else current_mqtt.password
        ok, message = test_mqtt_connection(
            server_addr, port_int, user, effective_password, ssl
        )
        if not ok:
            return Response(message, 400)
        device.settings.department = department
        device.settings.room = room
        device.settings.mqtt_settings.server = server_addr
        device.settings.mqtt_settings.port = port_int
        device.settings.mqtt_settings.user = user
        device.settings.mqtt_settings.ssl = ssl
        if password:
            device.settings.mqtt_settings.password = password
        save_settings(device.settings)
        device.settings_missing = False
        return {"status": "ok", "message": "MQTT checked and saved (effective on next cycle)"}

    @app.route("/api/settings/led", methods=["POST"])
    @protect
    def save_led(req):
        data = req.json or {}
        roles = (
            "alive", "measurement", "config_ap", "config_sta",
            "network", "error", "factory_reset",
        )
        led_data = {}
        try:
            for role in roles:
                color = (data.get(f"{role}_color") or "").strip()
                brightness = data.get(f"{role}_brightness")
                if not color:
                    return Response(f"{role} color is required", 400)
                led_data[role] = {
                    "color": color,
                    "brightness": int(brightness),
                }
            led_settings = LedSettings(**led_data)
            led_settings.validate_unique_colors()
            device.settings.led_settings = led_settings
        except (ValueError, TypeError) as e:
            return Response(str(e), 400)

        save_settings(device.settings)
        device.settings_missing = False
        device.restore_led_indicator()
        return {"status": "ok", "message": "LED settings saved"}

    @app.route("/api/led/preview", methods=["POST"])
    @protect
    def preview_led(req):
        data = req.json or {}
        try:
            role = LedRole(
                color=(data.get("color") or "").strip(),
                brightness=int(data.get("brightness")),
            )
            device.preview_led(role.color, role.brightness)
        except (ValueError, TypeError) as e:
            return Response(str(e), 400)
        return {"status": "ok"}

    @app.route("/api/led/restore", methods=["POST"])
    @protect
    def restore_led(req):
        device.restore_led_indicator()
        return {"status": "ok"}


    import asyncio as _asyncio
    from web.wifi_async import (
        get_scan_state, get_test_state, run_scan, run_test,
    )

    @app.route("/api/wifi/scan/start", methods=["POST"])
    @protect
    def wifi_scan_start(req):
        state = get_scan_state()
        if state["status"] in ("scheduled", "in_progress"):
            return state
        state["status"] = "scheduled"
        state["error"] = None
        ap_ssid, ap_password = current_ap_credentials()
        _asyncio.create_task(run_scan(ap_ssid, ap_password))
        return {"status": "scheduled"}

    @app.route("/api/wifi/scan/result")
    @protect
    def wifi_scan_result(req):
        return get_scan_state()

    @app.route("/api/wifi/scan")
    @protect
    def wifi_scan(req):
        """
        Backward-compat: старий ендпоінт для scan. Повертає поточний
        стан scan_state. Frontend може використовувати або це, або
        новий /api/wifi/scan/result -- обидва повертають однакову структуру.
        """
        return get_scan_state()

    @app.route("/api/wifi/test", methods=["POST"])
    @protect
    def wifi_test_start(req):
        data = req.json or {}
        ssid = (data.get("ssid") or "").strip()
        password = data.get("password") or ""
        if not ssid:
            return Response("SSID required", 400)
        if not password and ssid == device.settings.wifi_settings.ssid:
            password = device.settings.wifi_settings.password
        if not password:
            return Response("Password required", 400)
        state = get_test_state()
        if state["status"] in ("scheduled", "in_progress"):
            return state
        state["status"] = "scheduled"
        state["error"] = None
        state["result"] = None
        ap_ssid, ap_password = current_ap_credentials()
        _asyncio.create_task(run_test(ssid, password, ap_ssid, ap_password))
        return {"status": "scheduled"}

    @app.route("/api/wifi/test/result")
    @protect
    def wifi_test_result(req):
        return get_test_state()

    @app.route("/api/settings/parameters", methods=["POST"])
    @protect
    def save_parameters(req):
        data = req.json or {}
        units = data.get("units")
        ntp_server = data.get("ntp_server", "").strip()
        interval = data.get("mqtt_interval", data.get("measurement_interval"))
        try:
            if units is not None:
                device.settings.units = units
            if ntp_server:
                device.settings.ntp_server = ntp_server
            if interval is not None:
                device.settings.mqtt_interval = int(interval)
        except (ValueError, TypeError) as e:
            return Response(str(e), 400)
        save_settings(device.settings)
        device.settings_missing = False
        return {"status": "ok", "message": "Parameters saved"}

    @app.route("/api/settings/password/verify", methods=["POST"])
    @protect
    def verify_current_password(req):
        """
        Перевіряє поточний пароль для першого кроку form-password.
        UI використовує це щоб показати наступний крок (введення нового пароля).
        """
        data = req.json or {}
        current = data.get("current_password", "")
        if not check_password(current):
            return Response("Invalid password", 401)
        return {"status": "ok"}

    @app.route("/api/settings/password", methods=["POST"])
    @protect
    def change_password(req):
        """
        Зміна пароля. Очікує current_password + new_password + new_password2.
        Старий пароль перевіряється повторно (на випадок паралельних запитів).
        """
        data = req.json or {}
        current = data.get("current_password", "")
        new_pw  = data.get("new_password", "")
        new_pw2 = data.get("new_password2", "")
        if not check_password(current):
            return Response("Invalid password", 401)
        if len(new_pw) < MIN_PW_LENGTH:
            return Response(f"New password must be at least {MIN_PW_LENGTH} characters", 400)
        if new_pw != new_pw2:
            return Response("Passwords do not match", 400)
        set_password(new_pw)
        return {"status": "ok", "message": "Password changed"}
