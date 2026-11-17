"""
Unit tests for positions_manager.py module.

Tests the finished-media reset logic:
- is_finished: time-based decision (known length) with percent fallback
- get_position_of_media: finished media reads back as 0
- upsert_position / get_position_of_media roundtrip (including stored length)
"""
import json

import pytest

from vlc_interface import positions_manager


@pytest.fixture
def positions_file(tmp_path, monkeypatch):
    """Point the positions manager at a throwaway file."""
    path = tmp_path / "positions.json"
    path.write_text("{}")
    monkeypatch.setattr(positions_manager, "positions_file", path)
    return path


class TestIsFinished:
    """Time-based rule: finished when remaining <= min(5% of length, 3 min)."""

    def test_window_is_capped_at_max_seconds(self):
        # 2 hr movie: 5% would be 6 min, capped to 3 min
        assert positions_manager.finished_window(7200) == 180

    def test_window_scales_below_cap_for_short_media(self):
        # 30 min episode: 5% = 1.5 min, under the cap
        assert positions_manager.finished_window(1800) == 90

    def test_long_movie_beyond_window_is_not_finished(self):
        # 2 hr movie at 0.97 -> 3.6 min remaining, past the 3 min cutoff
        assert positions_manager.is_finished(0.97, 7200) is False

    def test_long_movie_within_window_is_finished(self):
        # 2 hr movie at 0.985 -> 1.8 min remaining
        assert positions_manager.is_finished(0.985, 7200) is True

    def test_short_episode_beyond_window_is_not_finished(self):
        # 30 min episode at 0.9 -> 3 min remaining, past the 1.5 min cutoff
        assert positions_manager.is_finished(0.9, 1800) is False

    def test_short_episode_within_window_is_finished(self):
        # 30 min episode at 0.96 -> 1.2 min remaining
        assert positions_manager.is_finished(0.96, 1800) is True

    def test_window_boundary_is_finished(self):
        position = 1 - positions_manager.finished_window(7200) / 7200
        assert positions_manager.is_finished(position, 7200) is True

    def test_start_of_media_is_not_finished(self):
        assert positions_manager.is_finished(0.0, 7200) is False

    def test_unknown_length_falls_back_to_percent_rule(self):
        assert positions_manager.is_finished(0.999935) is True
        assert positions_manager.is_finished(0.98) is True
        assert positions_manager.is_finished(0.9392) is False
        assert positions_manager.is_finished(0.75990563631058) is False

    def test_zero_length_falls_back_to_percent_rule(self):
        assert positions_manager.is_finished(0.98, 0) is True
        assert positions_manager.is_finished(0.42, 0) is False

    def test_none_position_is_never_finished(self):
        assert positions_manager.is_finished(None, 7200) is False


class TestGetPositionOfMedia:
    def test_unknown_media_returns_none(self, positions_file):
        assert positions_manager.get_position_of_media("missing.mkv") is None

    def test_finished_media_reads_back_as_zero(self, positions_file):
        positions_manager.upsert_position("done.mkv", 0.999935)
        assert positions_manager.get_position_of_media("done.mkv") == 0.0

    def test_time_finished_media_reads_back_as_zero(self, positions_file):
        positions_manager.upsert_position("credits.mkv", 0.985, length=7200)
        assert positions_manager.get_position_of_media("credits.mkv") == 0.0

    def test_partial_media_reads_back_as_stored(self, positions_file):
        positions_manager.upsert_position("partial.mkv", 0.42)
        assert positions_manager.get_position_of_media("partial.mkv") == pytest.approx(0.42)

    def test_legacy_entry_without_length_uses_percent_rule(self, positions_file):
        # simulate an old entry written before length was stored
        positions = json.loads(positions_file.read_text())
        positions["legacy.mkv"] = {"datetime": "2026-01-01T00:00:00", "position": 0.98}
        positions_file.write_text(json.dumps(positions))
        assert positions_manager.get_position_of_media("legacy.mkv") == 0.0

    def test_raw_position_and_length_are_preserved_on_disk(self, positions_file):
        positions_manager.upsert_position("done.mkv", 0.95, length=7200)
        raw = json.loads(positions_file.read_text())
        assert raw["done.mkv"]["position"] == pytest.approx(0.95)
        assert raw["done.mkv"]["length"] == pytest.approx(7200)
