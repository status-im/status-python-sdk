"""Media server port stays fixed after logout -> InitializeApplication -> login."""

import json
import threading
import time

import pytest
import requests
import urllib3
import websocket

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HTTP_BASE = "http://127.0.0.1:8080/statusgo"
WS_URL = "ws://127.0.0.1:8080/signals"
DATA_DIR = "./data-dir"
MEDIA_PORT = 8081
PASSWORD = "StatusSdkPortTest1"


class SignalBuffer:
    def __init__(self, url: str):
        self.url = url
        self.by_type: dict[str, list[dict]] = {}
        self._cond = threading.Condition()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def _run(self):
        while not self._stop:

            def on_message(_ws, raw: str):
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    return
                typ = msg.get("type")
                if not typ:
                    return
                with self._cond:
                    self.by_type.setdefault(typ, []).append(msg)
                    self._cond.notify_all()

            wsapp = websocket.WebSocketApp(self.url, on_message=on_message)
            wsapp.run_forever()
            if not self._stop:
                time.sleep(0.5)

    def count(self, signal_type: str) -> int:
        with self._cond:
            return len(self.by_type.get(signal_type, []))

    def wait_for(self, signal_type: str, since: int = 0, timeout: float = 90) -> dict:
        deadline = time.monotonic() + timeout
        with self._cond:
            while time.monotonic() < deadline:
                buf = self.by_type.get(signal_type, [])
                if len(buf) > since:
                    return buf[-1]
                self._cond.wait(timeout=0.5)
        raise TimeoutError(f"signal {signal_type!r} not received within {timeout}s")

    def latest_port(self, signal_type: str, since: int) -> int | None:
        with self._cond:
            signals = self.by_type.get(signal_type, [])[since:]
        for msg in reversed(signals):
            port = (msg.get("event") or {}).get("port")
            if port is not None:
                return int(port)
        return None

    def close(self):
        self._stop = True


def post_json(path: str, payload: dict | None = None, retries: int = 5) -> dict:
    # A freshly started status-backend accepts TCP before it serves /statusgo,
    # so early calls can be reset. Retry through connection errors.
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.post(f"{HTTP_BASE}/{path}", json=payload or {}, timeout=60)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()
        except requests.ConnectionError as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"POST {path} failed after {retries} retries: {last_exc}")


def wait_backend_healthy(timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if requests.get("http://127.0.0.1:8080/health", timeout=5).status_code == 200:
                return
        except requests.RequestException as exc:
            last_exc = exc
        time.sleep(2)
    raise RuntimeError(f"backend not healthy within {timeout}s: {last_exc}")


def initialize() -> dict:
    return post_json(
        "InitializeApplication",
        {
            "dataDir": DATA_DIR,
            "apiLoggingEnabled": True,
            "mediaServerAddress": f"0.0.0.0:{MEDIA_PORT}",
            "mediaServerAdvertizeHost": "localhost",
            "mediaServerAdvertizePort": MEDIA_PORT,
        },
    )


def logout(signals: SignalBuffer | None = None) -> None:
    since = signals.count("node.stopped") if signals is not None else 0
    try:
        post_json("Logout")
    except requests.RequestException:
        return
    if signals is not None:
        try:
            signals.wait_for("node.stopped", since=since, timeout=30)
        except TimeoutError:
            pass


def media_server_health_ok(port: int) -> bool:
    try:
        r = requests.get(f"https://127.0.0.1:{port}/health", timeout=10, verify=False)
        return r.status_code == 200
    except requests.RequestException:
        return False


def observed_port(signals: SignalBuffer, since: int) -> int | None:
    signal_port = signals.latest_port("mediaserver.started", since)
    if signal_port is not None:
        return signal_port
    if media_server_health_ok(MEDIA_PORT):
        return MEDIA_PORT
    return None


def ensure_account(signals: SignalBuffer, init_data: dict) -> str:
    accounts = init_data.get("accounts") or []
    if accounts:
        return accounts[0]["key-uid"]

    # CreateAccountAndLogin also logs in; stop the node afterwards so the
    # caller can perform a clean LoginAccount.
    since = signals.count("node.login")
    post_json(
        "CreateAccountAndLogin",
        {
            "rootDataDir": DATA_DIR,
            "kdfIterations": 256000,
            "displayName": "PortCheck",
            "password": PASSWORD,
            "customizationColor": "primary",
            "wakuV2LightClient": False,
            "thirdpartyServicesEnabled": True,
            "logEnabled": True,
            "logLevel": "INFO",
        },
    )
    signals.wait_for("node.login", since=since)
    logout(signals)
    init_data = initialize()
    accounts = init_data.get("accounts") or []
    assert accounts, "no accounts after CreateAccountAndLogin"
    return accounts[0]["key-uid"]


def login(key_uid: str, signals: SignalBuffer) -> None:
    since = signals.count("node.login")
    post_json(
        "LoginAccount",
        {
            "keyUid": key_uid,
            "password": PASSWORD,
            "kdfIterations": 256000,
            "thirdpartyServicesEnabled": True,
        },
    )
    event = signals.wait_for("node.login", since=since)
    err = (event.get("event") or {}).get("error")
    if err:
        raise RuntimeError(f"login error: {err}")


@pytest.fixture
def signals():
    buf = SignalBuffer(WS_URL)
    yield buf
    buf.close()
    logout(buf)


def test_media_port_persists_across_logout_reinit(signals):
    wait_backend_healthy()
    logout(signals)
    since = signals.count("mediaserver.started")
    init_data = initialize()
    key_uid = ensure_account(signals, init_data)
    login(key_uid, signals)
    port1 = observed_port(signals, since)
    assert port1 == MEDIA_PORT, f"first login: expected {MEDIA_PORT}, got {port1}"

    logout(signals)
    since = signals.count("mediaserver.started")
    initialize()
    login(key_uid, signals)
    port2 = observed_port(signals, since)
    assert port2 == MEDIA_PORT, f"after re-init: expected {MEDIA_PORT}, got {port2}"
