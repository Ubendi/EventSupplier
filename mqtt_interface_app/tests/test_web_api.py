"""
Tests for the web API (web/app.py + routers).

Uses FastAPI's TestClient with stub VLC listener/emitter so no real VLC or
MQTT is touched. Positions are redirected to a temp directory.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dataclasses import dataclass

from web.app import create_app
from web.state import AppState
from web.app_settings import SettingsStore
from vlc_interface import positions_manager


@dataclass
class StubStatus:
    status: str = "ok"
    http_code: int | None = 200
    payload: dict | None = None
    error: str | None = None


def make_client(tmp_path, monkeypatch):
    """Fresh app + temp positions file per test."""
    positions_file = tmp_path / "positions.json"
    monkeypatch.setattr(positions_manager, "positions_file", positions_file)

    app_state = AppState()
    settings_store = SettingsStore(settings_file=tmp_path / "settings.json")

    listener = MagicMock()
    emitter = MagicMock()
    emitter.send = MagicMock(return_value=MagicMock(status="ok", message="cmd done", error=None))

    app = create_app(app_state, settings_store, listener, emitter)
    return TestClient(app), app_state, listener, emitter


@pytest.fixture
def client(tmp_path, monkeypatch):
    c, state, listener, emitter = make_client(tmp_path, monkeypatch)
    yield c


# ============================================================================
# health + events
# ============================================================================

class TestHealth:
    def test_health(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestEvents:
    def test_events_initially_empty(self, client):
        res = client.get("/api/v1/events")
        assert res.status_code == 200
        data = res.json()
        assert data["events"] == []
        assert data["last_id"] == 0

    def test_events_after_add(self, client):
        client.app.state.app_state.add_event("vlc_update", "something happened")
        res = client.get("/api/v1/events")
        events = res.json()["events"]
        assert len(events) == 1
        assert events[0]["message"] == "something happened"
        assert events[0]["topic"] == "vlc_update"

    def test_min_id_filters(self, client):
        state = client.app.state.app_state
        state.add_event("a", "one")
        state.add_event("a", "two")
        res = client.get("/api/v1/events?min_id=1")
        assert [e["message"] for e in res.json()["events"]] == ["two"]


# ============================================================================
# status
# ============================================================================

class TestStatus:
    def test_status_ok(self, client):
        listener = client.app.state.vlc_listener
        listener.get_status.return_value = StubStatus(payload={
            "state": "playing",
            "position": 0.42,
            "time": 252,
            "length": 600,
            "volume": 128,
            "rate": 1.0,
            "information": {"category": {"meta": {"filename": "movie.mkv"}}},
        })
        res = client.get("/api/v1/status")
        data = res.json()
        assert data["vlc"]["state"] == "playing"
        assert data["vlc"]["media"]["filename"] == "movie.mkv"
        assert "watcher" in data

    def test_status_unreachable(self, client):
        listener = client.app.state.vlc_listener
        listener.get_status.return_value = StubStatus(status="vlc_not_running", payload=None, error="VLC not running")
        data = client.get("/api/v1/status").json()
        assert data["vlc"]["state"] == "unreachable"
        assert "not running" in data["vlc"]["error"]


# ============================================================================
# vlc commands
# ============================================================================

class TestVlcCommands:
    def test_play(self, client):
        res = client.post("/api/v1/vlc/play")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_seek_valid(self, client):
        res = client.post("/api/v1/vlc/seek", json={"position": 50})
        assert res.json()["status"] == "ok"

    def test_seek_invalid(self, client):
        res = client.post("/api/v1/vlc/seek", json={"position": 150})
        assert res.status_code == 422

    def test_volume(self, client):
        res = client.post("/api/v1/vlc/volume", json={"volume": 40})
        assert res.json()["status"] == "ok"

    def test_commands_feed_events(self, client):
        client.post("/api/v1/vlc/play")
        events = client.get("/api/v1/events").json()["events"]
        assert any(e["topic"] == "vlc_control" for e in events)


# ============================================================================
# positions
# ============================================================================

class TestPositions:
    def test_list_empty(self, client):
        data = client.get("/api/v1/positions").json()
        assert data == {"count": 0, "items": []}

    def test_upsert_and_list(self, client):
        client.put("/api/v1/positions/movie.mkv", json={"position": 0.5, "length": 600})
        data = client.get("/api/v1/positions").json()
        assert data["count"] == 1
        item = data["items"][0]
        assert item["media_name"] == "movie.mkv"
        assert item["position_percent"] == 50.0
        assert item["remaining_seconds"] == 300
        assert item["finished"] is False

    def test_finished_entry(self, client):
        client.put("/api/v1/positions/done.mkv", json={"position": 1.0, "length": 600})
        item = client.get("/api/v1/positions?q=done").json()["items"][0]
        assert item["finished"] is True
        assert item["resumes_from_zero"] is True

    def test_get_missing_404(self, client):
        assert client.get("/api/v1/positions/nope.mkv").status_code == 404

    def test_reset(self, client):
        client.put("/api/v1/positions/reset.mkv", json={"position": 0.8, "length": 600})
        client.post("/api/v1/positions/reset.mkv/reset")
        assert client.get("/api/v1/positions/reset.mkv").json()["position"] == 0.0

    def test_delete(self, client):
        client.put("/api/v1/positions/gone.mkv", json={"position": 0.1})
        assert client.delete("/api/v1/positions/gone.mkv").status_code == 200
        assert client.delete("/api/v1/positions/gone.mkv").status_code == 404

    def test_invalid_position_422(self, client):
        assert client.put("/api/v1/positions/x.mkv", json={"position": 2.0}).status_code == 422

    def test_nested_media_name(self, client):
        client.put("/api/v1/positions/Show/S01E01.mkv", json={"position": 0.25})
        assert client.get("/api/v1/positions/Show/S01E01.mkv").json()["position"] == 0.25


# ============================================================================
# settings
# ============================================================================

class TestSettings:
    def test_get_masked(self, client):
        data = client.get("/api/v1/settings").json()
        assert data["settings"]["vlc_key"] == "********"
        assert "vlc_port" in data["settings"]

    def test_update_persists(self, client, tmp_path):
        res = client.put("/api/v1/settings", json={"watch_interval": 5})
        data = res.json()
        assert data["status"] == "ok"
        assert data["restart_required"] == []
        saved = (tmp_path / "settings.json").read_text()
        assert "5" in saved

    def test_update_restart_required(self, client):
        res = client.put("/api/v1/settings", json={"mqtt_port": 1884})
        assert set(res.json()["restart_required"]) == {"mqtt_port"}

    def test_update_invalid(self, client):
        res = client.put("/api/v1/settings", json={"watch_interval": 0.1})
        assert res.status_code == 422

    def test_update_unknown_key(self, client):
        res = client.put("/api/v1/settings", json={"nope": 1})
        assert res.status_code == 422
