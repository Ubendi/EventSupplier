"""VLC playback controls exposed to the web UI."""
import asyncio
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/vlc", tags=["vlc"])

BASIC_COMMANDS = {"play", "pause", "stop"}


class SeekBody(BaseModel):
    position: float = Field(ge=0, le=100, description="Percent into the media")


class VolumeBody(BaseModel):
    volume: int = Field(ge=0, le=100, description="Percent of max volume")


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
