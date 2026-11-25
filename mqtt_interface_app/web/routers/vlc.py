"""VLC playback controls exposed to the web UI."""
import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from vlc_interface.vlc_event_builder import VLCEventBuilder
from vlc_interface import subtitle_delay_manager
from helper.path_mapping import container_to_host

router = APIRouter(prefix="/api/v1/vlc", tags=["vlc"])

BASIC_COMMANDS = {"play", "pause", "stop"}


class SeekBody(BaseModel):
    position: float = Field(ge=0, le=100, description="Percent into the media")


class VolumeBody(BaseModel):
    volume: int = Field(ge=0, le=100, description="Percent of max volume")


class PlayFileBody(BaseModel):
    path: str = Field(description="Absolute path of the file (container path when in Docker)")


class SubtitleDelayBody(BaseModel):
    offset: float = Field(ge=-7200, le=7200, description="Absolute subtitle offset in seconds")
    media_name: str | None = Field(default=None, description="Defaults to the media currently playing")


async def _dispatch(request: Request, command: str, payload=None):
    emitter = request.app.state.vlc_emitter
    action = {"action": command, "payload": payload, "time": time.time()}
    result = await asyncio.to_thread(emitter.send, action)
    request.app.state.app_state.add_event(
        "vlc_control", result.message, level="ok" if result.status == "ok" else "error"
    )
    return {"status": result.status, "message": result.message, "error": result.error}


@router.post("/play")
async def play(request: Request):
    return await _dispatch(request, "play")


@router.post("/pause")
async def pause(request: Request):
    return await _dispatch(request, "pause")


@router.post("/stop")
async def stop(request: Request):
    return await _dispatch(request, "stop")


@router.post("/seek")
async def seek(request: Request, body: SeekBody):
    return await _dispatch(request, "set_position", {"media_name": "web", "position": body.position})


@router.post("/volume")
async def volume(request: Request, body: VolumeBody):
    return await _dispatch(request, "set_volume", {"volume": body.volume})


def _host_view_path(request: Request, container_path: str) -> str:
    """Container path -> host path VLC should open (identity when not in Docker)."""
    store = request.app.state.settings_store
    return container_to_host(container_path, store.get("media_root"), store.get("media_host_path"))


async def _current_media_name(request: Request) -> str | None:
    listener = request.app.state.vlc_listener
    status = await asyncio.to_thread(listener.get_status)
    if status.status != "ok" or not status.payload:
        return None
    meta = status.payload.get("information", {}).get("category", {}).get("meta", {})
    return meta.get("filename")


@router.post("/play_file")
async def play_file(request: Request, body: PlayFileBody):
    file_path = Path(body.path)
    if not file_path.is_file():
        return {"status": "error", "message": f"File not found: {body.path}", "error": "file_not_found"}
    builder = VLCEventBuilder(None)
    action = builder.play_file_action(_host_view_path(request, str(file_path.resolve())))
    return await _dispatch(request, action["action"], action["payload"])


@router.post("/load_subtitle")
async def load_subtitle(request: Request, body: PlayFileBody):
    file_path = Path(body.path)
    if not file_path.is_file():
        return {"status": "error", "message": f"File not found: {body.path}", "error": "file_not_found"}
    builder = VLCEventBuilder(None)
    action = builder.load_subtitle_action(_host_view_path(request, str(file_path.resolve())))
    return await _dispatch(request, action["action"], action["payload"])


@router.post("/subtitle_delay")
async def subtitle_delay(request: Request, body: SubtitleDelayBody):
    media_name = body.media_name or (await _current_media_name(request))
    if not media_name:
        return {"status": "error", "message": "No media playing to adjust", "error": "no_media"}
    # Server-side store = single source of truth shared by every device
    await asyncio.to_thread(subtitle_delay_manager.set_delay, media_name, body.offset)
    result = await _dispatch(request, "set_subtitle_delay", {"offset": body.offset})
    result["media"] = media_name
    result["offset"] = body.offset
    return result


@router.get("/subtitle_delay")
async def get_subtitle_delay(request: Request):
    media_name = await _current_media_name(request)
    if not media_name:
        return {"status": "error", "message": "No media playing", "error": "no_media", "media": None, "offset": None}
    offset = await asyncio.to_thread(subtitle_delay_manager.get_delay, media_name)
    return {"status": "ok", "media": media_name, "offset": offset}
