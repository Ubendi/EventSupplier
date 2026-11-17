"""nCore tracker endpoints: status, login, search and torrent download."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ncore_interface.ncore_service import (
    NcoreNotConfigured,
    NcoreService,
)
from ncoreparser.error import (
    NcoreConnectionError,
    NcoreCredentialError,
    NcoreDownloadError,
    NcoreParserError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ncore", tags=["ncore"])


class LoginBody(BaseModel):
    username: str | None = None
    password: str | None = None


class DownloadBody(BaseModel):
    id: str = Field(min_length=1, description="Torrent id from the search results")


def _service(request: Request) -> NcoreService:
    return request.app.state.ncore_service


def _error_response(ex: Exception):
    if isinstance(ex, NcoreNotConfigured):
        return JSONResponse(status_code=400, content={"detail": str(ex)})
    if isinstance(ex, NcoreCredentialError):
        return JSONResponse(status_code=401, content={"detail": str(ex)})
    if isinstance(ex, NcoreConnectionError):
        return JSONResponse(status_code=502, content={"detail": f"nCore connection failed: {ex}"})
    if isinstance(ex, (NcoreDownloadError, NcoreParserError)):
        return JSONResponse(status_code=400, content={"detail": str(ex)})
    logger.error("Unexpected nCore error: %s", ex, exc_info=ex)
    return JSONResponse(status_code=500, content={"detail": "Internal nCore error"})


@router.get("/status")
async def status(request: Request):
    service = _service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"detail": "nCore service is disabled"})
    try:
        return await service.status()
    except Exception as ex:
        return _error_response(ex)


@router.post("/login")
async def login(request: Request, body: LoginBody | None = None):
    service = _service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"detail": "nCore service is disabled"})
    body = body or LoginBody()
    try:
        result = await service.login(
            username=body.username.strip() if body.username else None,
            password=body.password if body.password else None,
        )
        request.app.state.app_state.add_event("ncore", result["message"], level="ok")
        return result
    except Exception as ex:
        request.app.state.app_state.add_event("ncore", f"Login failed: {ex}", level="error")
        return _error_response(ex)


@router.post("/logout")
async def logout(request: Request):
    service = _service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"detail": "nCore service is disabled"})
    try:
        return await service.logout()
    except Exception as ex:
        return _error_response(ex)


@router.get("/search")
async def search(
    request: Request,
    pattern: str = "",
    type: str = "all_own",
    where: str = "name",
    sort_by: str = "upload",
    sort_order: str = "DESC",
    page: int = 1,
):
    service = _service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"detail": "nCore service is disabled"})
    if not pattern.strip():
        return JSONResponse(status_code=422, content={"detail": "pattern is required"})
    if not 1 <= page <= 100:
        return JSONResponse(status_code=422, content={"detail": "page must be 1-100"})
    try:
        return await service.search(
            pattern=pattern,
            type=type,
            where=where,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
        )
    except Exception as ex:
        return _error_response(ex)


@router.post("/download")
async def download(request: Request, body: DownloadBody):
    service = _service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"detail": "nCore service is disabled"})
    try:
        result = await service.download(body.id)
        request.app.state.app_state.add_event("ncore", result["message"], level="ok")
        return result
    except Exception as ex:
        request.app.state.app_state.add_event("ncore", f"Download failed: {ex}", level="error")
        return _error_response(ex)
