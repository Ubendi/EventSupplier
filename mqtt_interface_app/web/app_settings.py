"""
Application settings: built-in defaults, overridden by environment variables,
overridden again by a persisted JSON file (edited via the web UI or by hand).

Fields whose change requires a process restart are flagged via
RESTART_REQUIRED_KEYS so the UI can show a hint after saving.
"""
import json
import os
import threading
from pathlib import Path

# App data lives in data/ next to main.py, resolved from this file's
# location so startup CWD doesn't matter
APP_ROOT = Path(__file__).parent.parent
SETTINGS_DIR = Path(os.getenv("APP_DATA_DIR", str(APP_ROOT / "data")))
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# key -> type
SETTING_TYPES = {
    "vlc_host": str,
    "vlc_port": int,
    "vlc_key": str,
    "mqtt_host": str,
    "mqtt_port": int,
    "subtitle_language": str,
    "watch_interval": float,
    "web_host": str,
    "web_port": int,
    "ncore_username": str,
    "ncore_password": str,
    "ncore_download_dir": str,
    "media_root": str,
    "media_host_path": str,
    "qbt_username": str,
    "qbt_password": str,
}

DEFAULTS = {
    "vlc_host": "http://localhost",
    "vlc_port": 8080,
    "vlc_key": "pwd1234",
    "mqtt_host": "localhost",
    "mqtt_port": 1883,
    "subtitle_language": "English",    "watch_interval": 2.0,
    "web_host": "0.0.0.0",
    "web_port": 8081,
    "ncore_username": "",
    "ncore_password": "",
    "ncore_download_dir": str(APP_ROOT / "data" / "torrents"),
    "media_root": str(APP_ROOT),
    # Host-side twin of media_root; used when the app runs in Docker and the
    # host media folder is mounted at media_root (empty = no mapping)
    "media_host_path": "",
    "qbt_username": "",
    "qbt_password": "",
}

# Env var -> settings key
ENV_MAP = {
    "VLC_HOST": "vlc_host",
    "VLC_PORT": "vlc_port",
    "VLC_KEY": "vlc_key",
    "MQTT_HOST": "mqtt_host",
    "MQTT_PORT": "mqtt_port",
    "NCORE_USERNAME": "ncore_username",
    "NCORE_PASSWORD": "ncore_password",
    "QBT_USERNAME": "qbt_username",
    "QBT_PASSWORD": "qbt_password",
}

SECRET_KEYS = {"vlc_key", "ncore_password", "qbt_username", "qbt_password"}

# Changing these needs the watcher (or web server) to reconnect
RESTART_REQUIRED_KEYS = {"vlc_host", "vlc_port", "vlc_key", "mqtt_host", "mqtt_port", "web_host", "web_port"}


def _coerce(key: str, value):
    expected = SETTING_TYPES[key]
    if expected is float:
        return float(value)
    if expected is int:
        return int(float(value))
    return str(value)


class SettingsStore:
    """Thread-safe settings holder with JSON persistence."""

    def __init__(self, settings_file: Path = SETTINGS_FILE):
        self.settings_file = settings_file
        self._lock = threading.Lock()
        self._settings = dict(DEFAULTS)
        self._apply_env_overrides()
        self._load_overrides()

    def _load_env_file(self) -> dict:
        """Optional ENV_FILE setting for direct (non-Docker) runs: a dotenv
        file whose values apply where process env vars are unset."""
        path = os.getenv("ENV_FILE")
        if not path:
            return {}
        values = {}
        try:
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip()
        except OSError:
            pass
        return values

    def _apply_env_overrides(self):
        file_values = self._load_env_file()
        for env_key, settings_key in ENV_MAP.items():
            raw = os.getenv(env_key)
            if raw is None:
                raw = file_values.get(env_key)
            if raw is not None and settings_key in SETTING_TYPES:
                try:
                    self._settings[settings_key] = _coerce(settings_key, raw)
                except (TypeError, ValueError):
                    # Malformed env value: keep the default
                    pass

    def _load_overrides(self):
        try:
            if self.settings_file.exists():
                with open(self.settings_file) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if key in SETTING_TYPES and isinstance(value, SETTING_TYPES[key]):
                            self._settings[key] = value
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable settings file: fall back to env/defaults
            pass

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._settings)

    def get(self, key: str):
        with self._lock:
            return self._settings[key]

    def update(self, updates: dict) -> tuple[dict, list[str]]:
        """Validated update; returns (updated_keys, restart_required_keys)."""
        errors = {}
        valid = {}
        for key, value in updates.items():
            if key not in SETTING_TYPES:
                errors[key] = "unknown setting"
                continue
            try:
                coerced = _coerce(key, value)
            except (TypeError, ValueError):
                errors[key] = f"expected {SETTING_TYPES[key].__name__}"
                continue
            if key == "vlc_port" and not (1 <= coerced <= 65535):
                errors[key] = "port must be 1-65535"
                continue
            if key == "mqtt_port" and not (1 <= coerced <= 65535):
                errors[key] = "port must be 1-65535"
                continue
            if key == "watch_interval" and coerced < 0.5:
                errors[key] = "must be at least 0.5"
                continue
            valid[key] = coerced

        if errors:
            raise ValueError(errors)

        with self._lock:
            self._settings.update(valid)
            self._save()

        restart_required = [k for k in valid if k in RESTART_REQUIRED_KEYS]
        return list(valid.keys()), restart_required

    def masked(self) -> dict:
        """Public view with secrets redacted, for the web API."""
        data = self.get_all()
        for key in SECRET_KEYS:
            if data.get(key):
                data[key] = "*" * 8
        return data

    def _save(self):
        # Secrets are never persisted: they come from env vars (Docker/env
        # file) or from in-memory state set via the API for the current run.
        persistable = {k: v for k, v in self._settings.items() if k not in SECRET_KEYS}
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.settings_file, "w") as f:
            json.dump(persistable, f, indent=4)
