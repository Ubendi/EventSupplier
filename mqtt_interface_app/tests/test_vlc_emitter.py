"""
Unit tests for the new VLCEmitter commands (play_file, load_subtitle,
set_subtitle_delay) and their VLC HTTP request wiring, with requests.get
patched so no real VLC is needed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

from vlc_interface.vlc_event_builder import VLCEventBuilder
from vlc_interface.vlc_emitter import VLCEmitter


@pytest.fixture
def emitter():
    listener = MagicMock()
    builder = VLCEventBuilder(listener)
    em = VLCEmitter("http://localhost", 8080, "pwd", builder)
    em._mock_requests = MagicMock()
    return em


class TestEmitterCommands:
    def test_play_file_sends_in_play_with_file_uri(self, emitter, monkeypatch):
        calls = []
        monkeypatch.setattr("vlc_interface.vlc_emitter.requests.get",
                            lambda url, auth: calls.append(url))
        result = emitter.send(emitter.vlc_event_builder.play_file_action("C:/media/movie 1.mkv"))
        assert result.status == "ok"
        assert len(calls) == 1
        assert "command=in_play" in calls[0]
        assert "movie%201.mkv" in calls[0]  # spaces must be encoded

    def test_load_subtitle_sends_addsubtitle(self, emitter, monkeypatch):
        calls = []
        monkeypatch.setattr("vlc_interface.vlc_emitter.requests.get",
                            lambda url, auth: calls.append(url))
        result = emitter.send(emitter.vlc_event_builder.load_subtitle_action("C:/media/movie.srt"))
        assert result.status == "ok"
        assert "command=addsubtitle" in calls[0]
        assert "movie.srt" in calls[0]

    def test_subtitle_delay_sends_subdelay(self, emitter, monkeypatch):
        calls = []
        monkeypatch.setattr("vlc_interface.vlc_emitter.requests.get",
                            lambda url, auth: calls.append(url))
        result = emitter.send(emitter.vlc_event_builder.set_subtitle_delay_action(-2.5))
        assert result.status == "ok"
        assert "command=subdelay&val=-2.5" in calls[0]

    def test_delay_message_includes_sign(self, emitter, monkeypatch):
        monkeypatch.setattr("vlc_interface.vlc_emitter.requests.get", lambda url, auth: None)
        result = emitter.send(emitter.vlc_event_builder.set_subtitle_delay_action(1.0))
        assert "+1.0s" in result.message
