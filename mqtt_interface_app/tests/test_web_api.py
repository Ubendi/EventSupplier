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
from vlc_interface import positions_manager, subtitle_delay_manager


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

    delays_file = tmp_path / "subtitle_delays.json"
    monkeypatch.setattr(subtitle_delay_manager, "delays_file", delays_file)

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


# ============================================================================
# file browsing + open-in-vlc
# ============================================================================

def make_media_tree(tmp_path):
    media = tmp_path / "media"
    media.mkdir(exist_ok=True)
    (media / "movie.mkv").write_bytes(b"x")
    (media / "movie.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    (media / "notes.txt").write_text("ignored")
    sub = media / "season1"
    sub.mkdir(exist_ok=True)
    (sub / "ep1.mkv").write_bytes(b"x")
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.mkv").write_bytes(b"x")
    return media, sub, outside


def set_roots(client, tmp_path, listener=None, media=None, media_host_path=None):
    store = client.app.state.settings_store
    store.update({"media_root": str(media or tmp_path / "media")})
    if media_host_path is not None:
        store.update({"media_host_path": media_host_path})
    if listener is not None:
        listener.get_playlist.return_value = StubStatus(status="vlc_not_running", payload=None,
                                                        error="VLC not running")


class TestFileBrowser:
    def test_default_lists_media_root(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        data = client.get("/api/v1/files/browser").json()
        assert data["path"] == str(media)
        names = [f["name"] for f in data["files"]]
        assert names == ["movie.mkv", "movie.srt"]
        assert data["files"][0]["type"] == "video"
        assert data["files"][1]["type"] == "subtitle"
        dirs = [d["name"] for d in data["directories"]]
        assert dirs == ["season1"]

    def test_traversal_outside_roots_rejected(self, client, tmp_path):
        media, _, outside = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        data = client.get("/api/v1/files/browser", params={"path": str(outside)}).json()
        assert data["path"] is None
        assert "outside" in data["message"]

    def test_subdirectory_browse(self, client, tmp_path):
        media, sub, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        data = client.get("/api/v1/files/browser", params={"path": str(sub)}).json()
        assert data["path"] == str(sub)
        assert [f["name"] for f in data["files"]] == ["ep1.mkv"]
        assert data["parent"] == str(media)

    def test_default_is_current_media_folder(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        listener = client.app.state.vlc_listener
        listener.get_playlist.return_value = StubStatus(status="ok", payload={
            "children": [{"name": "Playlist", "children": [
                {"name": "old.mkv", "uri": "file:///C:/somewhere/other.mkv"},
                {"name": "current.mkv", "uri": media.joinpath("movie.mkv").as_uri(), "current": "current"},
            ]}]
        })
        data = client.get("/api/v1/files/browser").json()
        assert data["path"] == str(media)


class TestOpenInVlc:
    def test_play_file(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        res = client.post("/api/v1/vlc/play_file", json={"path": str(media / "movie.mkv")})
        assert res.json()["status"] == "ok"
        emitter = client.app.state.vlc_emitter
        sent = emitter.send.call_args[0][0]
        assert sent["action"] == "play_file"
        assert sent["payload"]["uri"].lower().startswith("file:")

    def test_play_file_missing(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        res = client.post("/api/v1/vlc/play_file", json={"path": str(media / "nope.mkv")})
        assert res.json()["status"] == "error"

    def test_load_subtitle(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        res = client.post("/api/v1/vlc/load_subtitle", json={"path": str(media / "movie.srt")})
        assert res.json()["status"] == "ok"
        sent = client.app.state.vlc_emitter.send.call_args[0][0]
        assert sent["action"] == "load_subtitle"

    def test_subtitle_delay(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        client.app.state.vlc_listener.get_status.return_value = StubStatus(payload={
            "state": "playing",
            "information": {"category": {"meta": {"filename": "movie.mkv"}}},
        })
        res = client.post("/api/v1/vlc/subtitle_delay", json={"offset": -1.5})
        assert res.json()["status"] == "ok"
        assert res.json()["media"] == "movie.mkv"
        sent = client.app.state.vlc_emitter.send.call_args[0][0]
        assert sent["action"] == "set_subtitle_delay"
        assert sent["payload"]["offset"] == -1.5

    def test_subtitle_delay_bounds(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        assert client.post("/api/v1/vlc/subtitle_delay", json={"offset": 99999}).status_code == 422

    def test_subtitle_delay_no_media(self, client, tmp_path):
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        client.app.state.vlc_listener.get_status.return_value = StubStatus(
            status="vlc_not_running", payload=None, error="VLC not running")
        res = client.post("/api/v1/vlc/subtitle_delay", json={"offset": 1})
        assert res.json()["status"] == "error"

    def test_subtitle_delay_persisted_and_shared(self, client, tmp_path):
        """The offset lives on the server: any device reading status sees it."""
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media)
        client.app.state.vlc_listener.get_status.return_value = StubStatus(payload={
            "state": "playing",
            "information": {"category": {"meta": {"filename": "movie.mkv"}}},
        })
        client.post("/api/v1/vlc/subtitle_delay", json={"offset": 1.5})
        data = client.get("/api/v1/status").json()
        assert data["vlc"]["subtitle_delay"] == 1.5
        got = client.get("/api/v1/vlc/subtitle_delay").json()
        assert got["offset"] == 1.5

    def test_play_file_maps_container_to_host_path(self, client, tmp_path):
        """In Docker the browser sees mounted paths but VLC gets host paths."""
        media, _, _ = make_media_tree(tmp_path)
        set_roots(client, tmp_path, media=media, media_host_path="D:/Videos")
        res = client.post("/api/v1/vlc/play_file", json={"path": str(media / "movie.mkv")})
        assert res.json()["status"] == "ok"
        sent = client.app.state.vlc_emitter.send.call_args[0][0]
        assert sent["payload"]["uri"] == Path("D:/Videos/movie.mkv").as_uri()

    def test_default_start_maps_host_media_path(self, client, tmp_path):
        """VLC's host-side current media path maps into the container for browsing."""
        media, _, _ = make_media_tree(tmp_path)
        # Host folder "/host/media" mounted at media_root in the container
        set_roots(client, tmp_path, media=media, media_host_path="/host/media")
        listener = client.app.state.vlc_listener
        listener.get_playlist.return_value = StubStatus(status="ok", payload={
            "children": [{"name": "Playlist", "children": [
                {"name": "movie.mkv", "uri": "file:///host/media/movie.mkv", "current": "current"},
            ]}]
        })
        data = client.get("/api/v1/files/browser").json()
        assert data["path"] == str(media)
