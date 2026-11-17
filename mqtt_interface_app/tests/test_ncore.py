"""
Tests for the nCore integration (ncore_interface + web/routers/ncore.py).

The ncoreparser.AsyncClient is mocked so no real tracker is contacted.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from web.app import create_app
from web.state import AppState
from web.app_settings import SettingsStore, SECRET_KEYS
from ncore_interface.ncore_service import NcoreService, NcoreNotConfigured
from ncoreparser.error import NcoreCredentialError, NcoreConnectionError, NcoreParserError


class FakeTorrent:
    """Mimics ncoreparser.torrent.Torrent's mapping interface."""

    def __init__(self, torrent_id="123"):
        self._details = {
            "id": torrent_id,
            "title": "Fake Torrent",
            "key": "abc",
            "size": "1.50 GiB",
            "type": "hd",
            "date": "2026-01-01",
            "seed": "10",
            "leech": "2",
            "url": f"https://ncore.pro/torrents.php?action=details&id={torrent_id}",
        }

    def __getitem__(self, key):
        return self._details[key]

    def keys(self):
        return list(self._details.keys())


def make_client(tmp_path, monkeypatch=None, **setting_overrides):
    settings_store = SettingsStore(settings_file=tmp_path / "settings.json")
    settings_store.update({"ncore_username": "user", "ncore_password": "pass"})
    if setting_overrides:
        settings_store.update(setting_overrides)

    service = NcoreService(settings_store)
    app = create_app(AppState(), settings_store, MagicMock(), MagicMock(), ncore_service=service)
    return TestClient(app), service, settings_store


@pytest.fixture
def patched_async_client():
    """Patch AsyncClient in the service module; returns the fake client instance."""
    with patch("ncore_interface.ncore_service.AsyncClient") as client_cls:
        client = MagicMock()
        client.login = AsyncMock(return_value={})
        client.search = AsyncMock(
            return_value=MagicMock(torrents=[FakeTorrent()], num_of_pages=3)
        )
        client.logout = AsyncMock(return_value=None)
        client_aclose = AsyncMock(return_value=None)
        client.aclose = client_aclose
        client_cls.return_value = client
        yield client


# ============================================================================
# settings
# ============================================================================

class TestNcoreSettings:
    def test_settings_keys_exist(self, tmp_path):
        store = SettingsStore(settings_file=tmp_path / "settings.json")
        settings = store.get_all()
        assert "ncore_username" in settings
        assert "ncore_password" in settings
        assert "ncore_download_dir" in settings

    def test_password_is_masked(self, tmp_path):
        store = SettingsStore(settings_file=tmp_path / "settings.json")
        store.update({"ncore_username": "user", "ncore_password": "sekret"})
        masked = store.masked()
        assert masked["ncore_password"] == "*" * 8
        assert "ncore_password" in SECRET_KEYS

    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NCORE_USERNAME", "envuser")
        monkeypatch.setenv("NCORE_PASSWORD", "envpass")
        store = SettingsStore(settings_file=tmp_path / "settings.json")
        assert store.get("ncore_username") == "envuser"
        assert store.get("ncore_password") == "envpass"


# ============================================================================
# service
# ============================================================================

class TestNcoreService:
    def test_not_configured_raises(self, tmp_path):
        store = SettingsStore(settings_file=tmp_path / "settings.json")
        service = NcoreService(store)
        assert not service.is_configured()
        import asyncio
        with pytest.raises(NcoreNotConfigured):
            asyncio.run(service._get_client())

    def test_search_maps_fields(self, tmp_path, patched_async_client):
        client, service, store = make_client(tmp_path)
        service._client = patched_async_client
        service._logged_in = True
        result = client.get("/api/v1/ncore/search?pattern=test")
        assert result.status_code == 200
        body = result.json()
        assert body["num_of_pages"] == 3
        torrent = body["torrents"][0]
        assert torrent["id"] == "123"
        assert torrent["title"] == "Fake Torrent"
        assert torrent["size"] == "1.50 GiB"
        assert torrent["url"].endswith("id=123")

    def test_search_invalid_type(self, tmp_path):
        client, service, _ = make_client(tmp_path)
        result = client.get("/api/v1/ncore/search?pattern=test&type=not_a_type")
        assert result.status_code == 400

    def test_search_empty_pattern(self, tmp_path):
        client, service, _ = make_client(tmp_path)
        result = client.get("/api/v1/ncore/search?pattern=")
        assert result.status_code == 422

    def test_download_writes_torrent_file(self, tmp_path, patched_async_client):
        download_dir = tmp_path / "torrents"
        client, service, store = make_client(tmp_path, ncore_download_dir=str(download_dir))
        service._client = patched_async_client
        service._logged_in = True
        torrent = FakeTorrent("777")
        patched_async_client.get_torrent = AsyncMock(return_value=torrent)
        patched_async_client.download = AsyncMock(
            side_effect=lambda t, path, override=False: str(
                Path(path) / f"{t._details['title'].replace(' ', '_')}.torrent"
            )
        )
        result = client.post("/api/v1/ncore/download", json={"id": "777"})
        assert result.status_code == 200
        body = result.json()
        assert body["download_dir"] == str(download_dir)
        patched_async_client.download.assert_awaited_once()

    def test_download_creates_dir(self, tmp_path, patched_async_client):
        download_dir = tmp_path / "nested" / "torrents"
        client, service, _ = make_client(tmp_path, ncore_download_dir=str(download_dir))
        service._client = patched_async_client
        service._logged_in = True
        patched_async_client.get_torrent = AsyncMock(return_value=FakeTorrent())
        patched_async_client.download = AsyncMock(return_value="x")

        result = client.post("/api/v1/ncore/download", json={"id": "1"})
        assert result.status_code == 200
        assert download_dir.exists()

    def test_credential_error_maps_to_401(self, tmp_path, patched_async_client):
        client, service, _ = make_client(tmp_path)
        service._client = patched_async_client
        service._logged_in = True
        patched_async_client.search = AsyncMock(
            side_effect=NcoreCredentialError("bad credentials")
        )
        result = client.get("/api/v1/ncore/search?pattern=test")
        assert result.status_code == 401

    def test_connection_error_maps_to_502(self, tmp_path, patched_async_client):
        client, service, _ = make_client(tmp_path)
        service._client = patched_async_client
        service._logged_in = True
        patched_async_client.search = AsyncMock(
            side_effect=NcoreConnectionError("network down")
        )
        result = client.get("/api/v1/ncore/search?pattern=test")
        assert result.status_code == 502

    def test_status_endpoint(self, tmp_path):
        client, service, _ = make_client(tmp_path)
        result = client.get("/api/v1/ncore/status")
        assert result.status_code == 200
        body = result.json()
        assert body["configured"] is True
        assert body["logged_in"] is False

    def test_download_error_maps_to_400(self, tmp_path, patched_async_client):
        download_dir = tmp_path / "torrents"
        client, service, _ = make_client(tmp_path, ncore_download_dir=str(download_dir))
        service._client = patched_async_client
        service._logged_in = True
        patched_async_client.get_torrent = AsyncMock(return_value=FakeTorrent())
        patched_async_client.download = AsyncMock(
            side_effect=_raise_download_exists
        )
        result = client.post("/api/v1/ncore/download", json={"id": "1"})
        assert result.status_code == 400


def _raise_download_exists(torrent, path, override=False):
    from ncoreparser.error import NcoreDownloadError
    raise NcoreDownloadError("already exists")


class TestLoginEndpoint:
    def test_login_success(self, tmp_path, patched_async_client):
        client, service, store = make_client(tmp_path)
        service._client = patched_async_client
        service._logged_in = True
        patched_async_client.login = AsyncMock(return_value={})
        # force a relogin by clearing the session
        result = client.post("/api/v1/ncore/login", json={"username": "newuser", "password": "newpass"})
        assert result.status_code == 200
        assert result.json()["status"] == "ok"
        assert store.get("ncore_username") == "newuser"
        patched_async_client.login.assert_awaited()

    def test_login_bad_credentials(self, tmp_path, patched_async_client):
        client, service, _ = make_client(tmp_path)
        service._client = patched_async_client
        patched_async_client.login = AsyncMock(
            side_effect=NcoreCredentialError("bad")
        )
        result = client.post("/api/v1/ncore/login", json={"username": "u", "password": "p"})
        assert result.status_code == 401
