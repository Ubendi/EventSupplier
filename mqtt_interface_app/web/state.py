"""
Shared live state between the VLC watcher and the web server.

Both run in the same asyncio process, so plain attribute access is safe for
the single-loop event model used here. The event log is a bounded deque so
long-running sessions don't grow memory.
"""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WatcherState:
    last_media: Optional[str] = None
    last_error: Optional[str] = None
    retry_count: int = 1
    is_retrying: bool = False
    vlc_status: str = "unknown"   # ok | vlc_not_running | no_active_media | ...
    loop_count: int = 0
    started_at: float = field(default_factory=time.time)


class AppState:
    """Holds watcher state and a bounded event feed for the web UI."""

    def __init__(self, max_events: int = 200):
        self.watcher = WatcherState()
        self.events: deque = deque(maxlen=max_events)
        self.event_seq: int = 0

    def add_event(self, topic: str, message: str, level: str = "info") -> dict:
        self.event_seq += 1
        entry = {
            "id": self.event_seq,
            "topic": topic,
            "message": message,
            "level": level,
            "time": time.time(),
        }
        self.events.append(entry)
        return entry

    def update_watcher(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self.watcher, key, value)

    def get_events(self, limit: int = 100, min_id: int = 0) -> list[dict]:
        events = [e for e in self.events if e["id"] > min_id]
        return list(reversed(events))[:limit]

    def snapshot(self) -> dict:
        w = self.watcher
        return {
            "last_media": w.last_media,
            "last_error": w.last_error,
            "retry_count": w.retry_count,
            "is_retrying": w.is_retrying,
            "vlc_status": w.vlc_status,
            "loop_count": w.loop_count,
            "uptime_seconds": time.time() - w.started_at,
        }
