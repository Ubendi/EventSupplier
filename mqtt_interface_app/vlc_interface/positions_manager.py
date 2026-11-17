import json
import datetime
import os
from pathlib import Path

root_dir = Path(__file__).parent

data_dir = Path(os.getenv("POSITION_FILE_DIR", str(root_dir.parent / "data")))
positions_file = data_dir / 'positions.json'

FINISHED_THRESHOLD = 0.97
FINISHED_WINDOW_PERCENT = 0.05
FINISHED_MAX_SECONDS = 3 * 60
FINISHED_POSITION = 0.0

def finished_window(length: float) -> float:
    return min(FINISHED_WINDOW_PERCENT * length, FINISHED_MAX_SECONDS)

def is_finished(position: float, length: float | None = None) -> bool:
    if position is None:
        return False
    if length and length > 0:
        remaining = length * (1 - position)
        return remaining <= finished_window(length) + 1e-9
    return position >= FINISHED_THRESHOLD

def position_changed(media_name: str, position: float, length: float | None = None) -> bool:
    """True if the stored entry differs from what was (re)reported."""
    entry = get_position_entry(media_name)
    if entry is None:
        return True
    return not (entry.get("position") == position and entry.get("length") == length)

def upsert_position(media_name: str, position: float, length: float | None = None) -> None:
    # Skip the rewrite when nothing changed (paused playback re-reports the
    # exact same fraction every poll)
    if not position_changed(media_name, position, length):
        return
    positions = _load_positions()
    positions[media_name] = {
        "datetime" : datetime.datetime.now().isoformat(),
        "position" : position,
        "length" : length
    }
    _save_positions(positions)

def delete_position(media_name: str) -> bool:
    """Remove a media entry entirely. Returns True if it existed."""
    positions = _load_positions()
    if media_name not in positions:
        return False
    del positions[media_name]
    _save_positions(positions)
    return True

def list_positions() -> dict:
    """Raw positions dict, keyed by media name."""
    return _load_positions()

def get_position_entry(media_name: str) -> dict | None:
    positions = _load_positions()
    return positions.get(media_name)

def get_position_of_media(media_name: str) -> float | None:
    positions = _load_positions()
    if not media_name in positions:
        return None
    else:
        entry = positions[media_name]
        pos = entry["position"]
        if is_finished(pos, entry.get("length")):
            return FINISHED_POSITION
        return pos


def _load_positions():
    if not positions_file.exists():
        return {}
    with open(positions_file) as f:
        data = json.load(f)
        return data
    
def _save_positions(positions):
    positions_file.parent.mkdir(parents=True, exist_ok=True)
    with open(positions_file, 'w') as f:
        json.dump(positions, f, indent=4, default=str)
