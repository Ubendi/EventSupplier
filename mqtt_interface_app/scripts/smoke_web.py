import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, r"A:\Programming\EventSupplier\mqtt_interface_app")

from fastapi.testclient import TestClient
from web.app import create_app
from web.state import AppState
from web.app_settings import SettingsStore
from vlc_interface import positions_manager
from ncore_interface.ncore_service import NcoreService

tmp = Path(tempfile.mkdtemp())
monkey_positions_file = tmp / "positions.json"
positions_manager.positions_file = monkey_positions_file
positions_manager._save_positions({})

settings_store = SettingsStore(settings_file=tmp / "settings.json")
app_state = AppState()
ncore_service = NcoreService(settings_store)

listener = MagicMock()
listener.get_status.return_value = MagicMock(
    status="ok", payload={
        "state": "playing", "position": 0.37, "time": 250, "length": 680,
        "volume": 128, "rate": 1.0,
        "information": {"category": {"meta": {"filename": "demo.mkv"}}},
    }, error=None)

emitter = MagicMock()
emitter.send.return_value = MagicMock(status="ok", message="simulated", error=None)

client = TestClient(create_app(app_state, settings_store, listener, emitter, ncore_service=ncore_service))

checks = []

def check(name, condition):
    checks.append((name, bool(condition)))

r = client.get("/api/v1/health")
check("health 200", r.status_code == 200)

r = client.get("/api/v1/status")
check("status shows playing media", r.json()["vlc"]["media"]["filename"] == "demo.mkv")
check("status watcher snapshot present", "watcher" in r.json())

r = client.put("/api/v1/positions/demo.mkv", json={"position": 0.65, "length": 680})
check("upsert position", r.json()["status"] == "ok")
r = client.get("/api/v1/positions?q=demo")
check("list has entry", r.json()["count"] == 1)
item = r.json()["items"][0]
check("percent computed", abs(item["position_percent"] - 65.0) < 0.01)
check("remaining computed", item["remaining_seconds"] == round(680 * 0.35))
check("on-disk file created", monkey_positions_file.exists())

r = client.post("/api/v1/vlc/pause")
check("vlc pause via stub", r.json()["message"] == "simulated")

r = client.get("/api/v1/events")
check("control event recorded", any(e["topic"] == "vlc_control" for e in r.json()["events"]))

r = client.put("/api/v1/settings", json={"watch_interval": 4, "vlc_key": "newsecret"})
check("settings save", r.json()["status"] == "ok")
check("restart flag for vlc_key", "vlc_key" in r.json()["restart_required"])
check("masked response", r.json()["settings"]["vlc_key"] == "********")

r = client.get("/")
check("index served", r.status_code == 200 and b"EventSupplier" in r.content)
r = client.get("/js/app.js")
check("app.js served", r.status_code == 200)
r = client.get("/css/style.css")
check("style.css served", r.status_code == 200)

r = client.put("/api/v1/settings", json={"vlc_port": 99999})
check("port range rejected", r.status_code == 422)

r = client.delete("/api/v1/positions/demo.mkv")
check("delete position", r.status_code == 200)

r = client.get("/api/v1/ncore/status")
check("ncore status 200", r.status_code == 200)
check("ncore not configured in smoke", r.json()["configured"] is False)
check("ncore download dir present", bool(r.json()["download_dir"]))
r = client.get("/api/v1/ncore/search?pattern=x")
check("ncore unconfigured search 400", r.status_code == 400)
r = client.get("/")
check("ncore tab in html", b"data-tab=\"ncore\"" in r.content)
r = client.get("/js/app.js")
check("ncore js present", b"ncoreSearch" in r.content)

failed = [c for c in checks if not c[1]]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print(f"\n{len(checks) - len(failed)}/{len(checks)} smoke checks passed")
sys.exit(1 if failed else 0)
