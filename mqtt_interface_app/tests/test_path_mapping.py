"""
Unit tests for helper/path_mapping and the per-media subtitle delay store.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vlc_interface import subtitle_delay_manager
from helper.path_mapping import (
    container_to_host,
    file_name,
    host_to_container,
    map_path,
    path_to_uri,
)


class TestSubtitleDelayManager:
    @pytest.fixture(autouse=True)
    def temp_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subtitle_delay_manager, "delays_file", tmp_path / "delays.json")

    def test_missing_returns_none(self):
        assert subtitle_delay_manager.get_delay("movie.mkv") is None

    def test_set_get_roundtrip(self):
        subtitle_delay_manager.set_delay("movie.mkv", 1.5)
        assert subtitle_delay_manager.get_delay("movie.mkv") == 1.5

    def test_overwrite(self):
        subtitle_delay_manager.set_delay("movie.mkv", 1.5)
        subtitle_delay_manager.set_delay("movie.mkv", -0.5)
        assert subtitle_delay_manager.get_delay("movie.mkv") == -0.5

    def test_delete(self):
        subtitle_delay_manager.set_delay("movie.mkv", 1.0)
        subtitle_delay_manager.delete_delay("movie.mkv")
        assert subtitle_delay_manager.get_delay("movie.mkv") is None

    def test_persisted_across_calls(self):
        subtitle_delay_manager.set_delay("movie.mkv", 2.0)
        # File actually written
        assert subtitle_delay_manager.delays_file.exists()


class TestPathMapping:
    def test_map_disabled_when_roots_empty(self):
        assert map_path("/media/x.mkv", "", "D:/V") == "/media/x.mkv"
        assert map_path("/media/x.mkv", "/media", "") == "/media/x.mkv"

    def test_container_to_host(self):
        out = container_to_host("/media/Movies/film.mkv", "/media", "D:\\Videos")
        assert out.endswith("film.mkv")

    def test_missing_mapping_returns_path(self):
        assert container_to_host("/other/x.mkv", "/media", "D:\\Videos") == "/other/x.mkv"

    def test_round_trip(self):
        # Host paths normalize to the forward-slash form; both Path flavors
        # (and VLC's URIs) accept it
        host_root = "D:/Videos"
        host = f"{host_root}/Sub/film.mkv"
        container = host_to_container(host, "/media", host_root)
        assert container == "/media/Sub/film.mkv"
        assert container_to_host(container, "/media", host_root) == host

    def test_file_name_cross_platform(self):
        assert file_name("D:\\Media\\movie.mkv") == "movie.mkv"
        assert file_name("/media/movie.mkv") == "movie.mkv"

    def test_uri_windows_drive(self):
        assert path_to_uri("D:\\Media\\movie.mkv") == "file:///D:/Media/movie.mkv"

    def test_uri_posix(self):
        assert path_to_uri("/media/movie 1.mkv") == "file:///media/movie%201.mkv"
