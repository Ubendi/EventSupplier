"""Per-media subtitle delay storage, persisted to data/subtitle_delays.json.

The subtitle offset cannot be read back from VLC's HTTP status API, so the
app is the source of truth: it is shared between all devices (web UI, watch.
loop) and survives app and page reloads.
"""
import datetime
import json
import os
import threading
from pathlib import Path

root_dir = Path(__file__).parent

# Same data dir convention as positions_manager; overridable for tests/docker
data_dir = Path(os.getenv("SUBTITLE_DELAY_FILE_DIR", str(root_dir.parent / "data")))
delays_file = data_dir / "subtitle_delays.json"

_lock = threading.Lock()


def set_delay(media_name: str, offset: float) -> None:
    """Store the offset (seconds) for the given media."""
    with _lock:
        delays = _load()
        delays[media_name] = {
            "offset": round(float(offset), 3),
            "datetime": datetime.datetime.now().isoformat(),
        }
        _save(delays)


def get_delay(media_name: str) -> float | None:
    with _lock:
        entry = _load().get(media_name)
    if entry is None:
        return None
    try:
        return float(entry["offset"])
    except (KeyError, TypeError, ValueError):
        return None


def delete_delay(media_name: str) -> None:
    with _lock:
        delays = _load()
        if media_name in delays:
            del delays[media_name]
            _save(delays)


def _load() -> dict:
    if not delays_file.exists():
        return {}
    try:
        with open(delays_file, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(delays: dict) -> None:
    delays_file.parent.mkdir(parents=True, exist_ok=True)
    with open(delays_file, "w", encoding="utf-8") as f:
        json.dump(delays, f, indent=4)
