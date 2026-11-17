import json
import datetime
import os
from pathlib import Path

root_dir = Path(__file__).parent

# Positions live with the other app data (data/positions.json next to
# main.py). POSITION_FILE_DIR lets a deployment (tests, custom layout)
# redirect it to another directory without touching the module.
data_dir = Path(os.getenv("POSITION_FILE_DIR", str(root_dir.parent / "data")))
positions_file = data_dir / 'positions.json'

# Two-tier finished detection:
# 1. Time-based (used when the media length is known): the credits window is
#    5% of the runtime, capped at FINISHED_MAX_SECONDS, so it scales with the
#    media - about 1.5 min for a 30 min episode, 3 min for anything longer.
#    Media is finished when the remaining time falls inside that window.
# 2. Percent-based fallback (older entries without a stored length): position
#    at or above the threshold, sitting well below 1.0 because players stop
#    before the absolute end and credit skips leave residue around 0.94-0.98
#    (same idea as Plex/Jellyfin).
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
        # epsilon guards the float edge case where remaining is the window
        # value only up to rounding error
        return remaining <= finished_window(length) + 1e-9
    return position >= FINISHED_THRESHOLD

def upsert_position(media_name: str, position: float, length: float | None = None) -> None:
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
