
import json
import datetime
from pathlib import Path

root_dir = Path(__file__).parent
positions_file = root_dir / 'positions.json'

def upsert_position(media_name: str, position: float) -> None:
    positions = _load_positions()
    positions[media_name] = {
        "datetime" : datetime.datetime.now().isoformat(),
        "position" : position
    }
    _save_positions(positions)
    
def get_position_of_media(media_name: str) -> float | None:
    positions = _load_positions()
    if not media_name in positions:
        return None
    else:
        pos = positions[media_name]["position"]
        return pos


def _load_positions():
    with open(positions_file) as f:
        data = json.load(f)
        return data
    
def _save_positions(positions):
    with open(positions_file, 'w') as f:
        json.dump(positions, f, indent=4, default=str)