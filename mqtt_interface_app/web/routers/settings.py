"""Application settings, persisted to data/settings.json."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.app_settings import RESTART_REQUIRED_KEYS

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
async def get_settings(request: Request):
    store = request.app.state.settings_store
    return {
        "settings": store.masked(),
        "restart_required_keys": sorted(RESTART_REQUIRED_KEYS),
    }


@router.put("")
async def update_settings(request: Request):
    store = request.app.state.settings_store
    updates = await request.json()
    if not isinstance(updates, dict) or not updates:
        return JSONResponse(status_code=422, content={"detail": "Body must be a non-empty object"})
    try:
        updated, restart_required = store.update(updates)
    except ValueError as ex:
        return JSONResponse(status_code=422, content={"detail": ex.args[0]})
    return {
        "status": "ok",
        "updated": updated,
        "restart_required": restart_required,
        "settings": store.masked(),
    }
