"""FastAPI application factory for the EventSupplier web UI."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.state import AppState
from web.app_settings import SettingsStore
from web.routers import status, vlc, positions, settings, events, ncore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    app_state: AppState,
    settings_store: SettingsStore,
    vlc_listener,
    vlc_emitter,
    ncore_service=None,
) -> FastAPI:
    app = FastAPI(title="EventSupplier", version="1.0.0")

    # Dependencies; routers reach these via request.app.state
    app.state.app_state = app_state
    app.state.settings_store = settings_store
    app.state.vlc_listener = vlc_listener
    app.state.vlc_emitter = vlc_emitter
    app.state.ncore_service = ncore_service

    # API routers first: they take precedence over the static mount below
    app.include_router(status.router)
    app.include_router(vlc.router)
    app.include_router(positions.router)
    app.include_router(settings.router)
    app.include_router(events.router)
    app.include_router(ncore.router)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    # Web UI last so /api/* keeps priority
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
