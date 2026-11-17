"""Recent event feed (MQTT publishes, VLC controls, errors)."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/events")
async def get_events(request: Request, limit: int = 100, min_id: int = 0):
    limit = max(1, min(limit, 500))
    events = request.app.state.app_state.get_events(limit=limit, min_id=min_id)
    return {"last_id": max((e["id"] for e in events), default=0), "events": events}
