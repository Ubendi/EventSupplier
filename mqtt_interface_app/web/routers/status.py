"""Live VLC status + watcher state."""
import asyncio

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["status"])


def _serialize_status(payload: dict | None) -> dict:
    if not payload:
        return {"state": "unknown", "media": None}
    category = payload.get("information", {}).get("category", {})
    meta = category.get("meta", {})
    streams = [
        {
            "name": key,
            "type": info.get("Type"),
            "language": info.get("Language"),
            "description": info.get("Description"),
        }
        for key, info in category.items()
        if info.get("Type") in ("Video", "Audio", "Subtitle")
    ]
    return {
        "state": payload.get("state"),
        "media": {
            "filename": meta.get("filename"),
            "title": meta.get("title"),
        },
        "position": payload.get("position"),
        "time": payload.get("time"),
        "length": payload.get("length"),
        "volume": payload.get("volume"),
        "rate": payload.get("rate"),
        "streams": streams,
    }


@router.get("/status")
async def get_status(request: Request):
    listener = request.app.state.vlc_listener
    status = await asyncio.to_thread(listener.get_status)
    watcher = request.app.state.app_state.snapshot()

    if status.status == "ok":
        vlc = _serialize_status(status.payload)
    else:
        vlc = {"state": "unreachable", "media": None, "error": status.error}

    return {"vlc": vlc, "watcher": watcher}
