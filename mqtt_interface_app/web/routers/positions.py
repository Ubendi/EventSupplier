"""Positions CRUD over the shared positions.json store."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from vlc_interface import positions_manager

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


class PositionBody(BaseModel):
    position: float = Field(ge=0, le=1, description="Position as 0-1 fraction")
    length: float | None = Field(default=None, gt=0, description="Media length in seconds")


def _serialize(name: str, entry: dict) -> dict:
    position = entry.get("position", 0)
    length = entry.get("length")
    remaining = None
    if length and length > 0:
        remaining = round(length * (1 - position))
    return {
        "media_name": name,
        "datetime": entry.get("datetime"),
        "position": position,
        "length": length,
        "position_percent": round(position * 100, 2),
        "remaining_seconds": remaining,
        "finished": positions_manager.is_finished(position, length),
        "resumes_from_zero": (
            positions_manager.get_position_of_media(name) == positions_manager.FINISHED_POSITION
        ),
    }


@router.get("")
async def list_positions(request: Request):
    query = (request.query_params.get("q") or "").lower()
    raw = positions_manager.list_positions()
    items = [_serialize(name, entry) for name, entry in raw.items() if query in name.lower()]
    items.sort(key=lambda i: i["datetime"] or "", reverse=True)
    return {"count": len(items), "items": items}


@router.get("/{media_name:path}")
async def get_position(media_name: str):
    entry = positions_manager.get_position_entry(media_name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return _serialize(media_name, entry)


@router.put("/{media_name:path}")
async def upsert_position(media_name: str, body: PositionBody):
    positions_manager.upsert_position(media_name, body.position, body.length)
    return {"status": "ok", "media_name": media_name, "position": body.position}


@router.post("/{media_name:path}/reset")
async def reset_position(media_name: str):
    entry = positions_manager.get_position_entry(media_name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Media not found")
    positions_manager.upsert_position(media_name, 0.0, entry.get("length"))
    return {"status": "ok", "media_name": media_name, "position": 0.0}


@router.post("/{media_name:path}/mark_finished")
async def mark_finished(media_name: str):
    entry = positions_manager.get_position_entry(media_name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Media not found")
    # 1.0 always falls inside the finished window (or passes the percent
    # threshold), so this marks it finished regardless of stored length
    positions_manager.upsert_position(media_name, 1.0, entry.get("length"))
    return {"status": "ok", "media_name": media_name}


@router.delete("/{media_name:path}")
async def delete_position(media_name: str):
    deleted = positions_manager.delete_position(media_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media not found")
    return {"status": "ok", "deleted": media_name}
