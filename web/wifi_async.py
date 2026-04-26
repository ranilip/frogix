"""
wifi_async.py -- асинхронні операції з Wi-Fi радіо, які потребують
тимчасового вимкнення AP.

Чому окремий модуль:
    На CYW43 (Pico W / Pico 2 W) AP+STA не тримаються одночасно
    стабільно. Будь-яка операція яка вимагає STA (scan, test connect)
    змушує тимчасово вимкнути AP, виконати STA-op, увімкнути AP назад.
    Браузер при цьому втрачає Wi-Fi-зв'язок з пристроєм на ~5-15с,
    потім ОС автоматично перепідключається до thsensor AP.

Pattern:
    1. HTTP POST /api/wifi/<op>/start приходить
       handler планує `asyncio.create_task(run_op(...))`, відразу
       повертає 200 OK. Це дозволяє відповіді доїхати до клієнта
       до того як ми вимкнемо AP.
    2. Background task: sleep 800мс (response delivery) → AP off →
       STA op → AP on. Прогрес зберігається у module-level state dict.
    3. Frontend через ~5с робить GET /api/wifi/<op>/result. Якщо AP
       вже піднявся, отримує JSON з результатом. Якщо ні -- connection
       refused, frontend retry'ить.
"""

import asyncio

import network

from constants import (
    AP_SSID, AP_PASSWORD, AP_IP_ADDRESS,
    WIFI_CONNECTION_TIMEOUT,
)



_scan_state = {
    "status": "idle",     # idle | scheduled | in_progress | done | error
    "networks": [],
    "error": None,
}

_test_state = {
    "status": "idle",     # idle | scheduled | in_progress | done | error
    "result": None,       # ok | wrong_password | no_ap | fail | timeout
    "ip": None,
    "error": None,
}


def get_scan_state() -> dict:
    return _scan_state


def get_test_state() -> dict:
    return _test_state



async def _restart_ap(ap_ssid=AP_SSID, ap_password=AP_PASSWORD):
    """
    Вмикає AP назад після STA-операції. Використовується у finally
    щоб гарантувати повернення в AP-режим навіть якщо STA-op впала.
    """
    ap = network.WLAN(network.AP_IF)
    try:
        try:
            ap.ifconfig((AP_IP_ADDRESS, "255.255.255.0", AP_IP_ADDRESS, AP_IP_ADDRESS))
        except Exception:
            pass
        try:
            ap.config(
                essid=ap_ssid, password=ap_password,
                channel=6, authmode=network.AUTH_WPA_WPA2_PSK,
            )
        except Exception:
            ap.config(essid=ap_ssid, password=ap_password, channel=6)
        ap.active(True)
        for _ in range(20):
            if ap.active():
                return
            await asyncio.sleep_ms(100)
    except Exception as e:
        print(f"AP restart failed: {e}")



async def run_scan(ap_ssid=AP_SSID, ap_password=AP_PASSWORD):
    """
    Live Wi-Fi scan: AP off → STA up → scan → STA off → AP on.
    Результат у `_scan_state["networks"]`.
    """
    _scan_state["status"] = "scheduled"
    _scan_state["error"] = None

    await asyncio.sleep_ms(800)

    _scan_state["status"] = "in_progress"

    ap = network.WLAN(network.AP_IF)
    sta = network.WLAN(network.STA_IF)

    try:
        ap.active(False)
        await asyncio.sleep_ms(300)
        sta.active(True)
        await asyncio.sleep_ms(300)

        raw_results = sta.scan()
        networks = []
        seen = set()
        for n in raw_results:
            try:
                raw_ssid = n[0]
                if isinstance(raw_ssid, (bytes, bytearray)):
                    ssid = raw_ssid.decode("utf-8")
                else:
                    ssid = str(raw_ssid)
            except Exception:
                continue
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append({
                "ssid":    ssid,
                "rssi":    int(n[3]) if len(n) > 3 else 0,
                "secured": bool(n[4]) if len(n) > 4 else False,
            })
        networks.sort(key=lambda x: -x["rssi"])
        _scan_state["networks"] = networks

        try:
            sta.active(False)
        except Exception:
            pass

        _scan_state["status"] = "done"
        print(f"Live scan: {len(networks)} networks")

    except Exception as e:
        _scan_state["error"] = str(e)
        _scan_state["status"] = "error"
        print(f"Live scan failed: {e}")
        try:
            sta.active(False)
        except Exception:
            pass
    finally:
        await _restart_ap(ap_ssid, ap_password)



def _status_to_result(status_code: int) -> str:
    """
    Перетворює `network.WLAN.status()` код у рядок-результат.
    Коди MicroPython:
        STAT_GOT_IP        =  3  → "ok"
        STAT_CONNECTING    =  1
        STAT_IDLE          =  0
        STAT_CONNECT_FAIL  = -1  → "fail"
        STAT_NO_AP_FOUND   = -2  → "no_ap"
        STAT_WRONG_PASSWORD= -3  → "wrong_password"
    """
    if status_code >= 3:
        return "ok"
    if status_code == -3:
        return "wrong_password"
    if status_code == -2:
        return "no_ap"
    if status_code == -1:
        return "fail"
    return "fail"


async def run_test(ssid: str, password: str, ap_ssid=AP_SSID, ap_password=AP_PASSWORD):
    """
    Live Wi-Fi password test: AP off → STA connect → read status →
    STA off → AP on. Результат у `_test_state["result"]`.
    """
    _test_state["status"] = "scheduled"
    _test_state["error"] = None
    _test_state["result"] = None
    _test_state["ip"] = None

    await asyncio.sleep_ms(800)

    _test_state["status"] = "in_progress"

    ap = network.WLAN(network.AP_IF)
    sta = network.WLAN(network.STA_IF)

    try:
        ap.active(False)
        await asyncio.sleep_ms(300)
        sta.active(True)
        await asyncio.sleep_ms(300)

        try:
            sta.connect(ssid, password)
        except Exception as e:
            _test_state["error"] = str(e)
            _test_state["status"] = "error"
            try:
                sta.active(False)
            except Exception:
                pass
            return

        polled = 0
        max_polls = WIFI_CONNECTION_TIMEOUT * 2
        result = None
        while polled < max_polls:
            await asyncio.sleep_ms(500)
            polled += 1
            status_code = sta.status()
            if status_code >= 3:
                result = "ok"
                break
            if status_code < 0:
                result = _status_to_result(status_code)
                break

        if result is None:
            result = "timeout"

        if result == "ok":
            try:
                _test_state["ip"] = sta.ifconfig()[0]
            except Exception:
                _test_state["ip"] = None

        _test_state["result"] = result
        _test_state["status"] = "done"
        print(f"WiFi test for '{ssid}': {result}")

        try:
            sta.disconnect()
        except Exception:
            pass
        try:
            sta.active(False)
        except Exception:
            pass

    except Exception as e:
        _test_state["error"] = str(e)
        _test_state["status"] = "error"
        print(f"WiFi test failed: {e}")
        try:
            sta.active(False)
        except Exception:
            pass
    finally:
        await _restart_ap(ap_ssid, ap_password)
