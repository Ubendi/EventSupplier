"""
Async service wrapper around ncoreparser.AsyncClient.

Credentials come from the settings store (env vars / settings.json / web UI).
The client logs in lazily on first use and re-logins once when a stored
session turns out to be invalid, so no restart is needed after changing
credentials in the UI.
"""
import asyncio
import logging
from pathlib import Path

import httpx
from ncoreparser import AsyncClient, SearchParamType
from ncoreparser.data import ParamSeq, ParamSort, SearchParamWhere
from ncoreparser.error import (
    NcoreConnectionError,
    NcoreCredentialError,
    NcoreParserError,
)

logger = logging.getLogger(__name__)

# Torrent fields exposed to the web API
TORRENT_FIELDS = ["id", "title", "size", "type", "date", "seed", "leech"]

HTTP_TIMEOUT = 15
QBITTORRENT_URL = "http://host.docker.internal:8085"


class NcoreNotConfigured(Exception):
    """Raised when username or password is missing from settings."""


class QbittorrentNotConfigured(Exception):
    """Raised when qBittorrent Web UI credentials are missing."""


class QbittorrentError(Exception):
    """Raised when qBittorrent rejects or cannot accept a torrent."""


class QbittorrentAuthenticationError(QbittorrentError):
    """Raised when qBittorrent rejects the configured credentials."""


async def add_torrent_to_qbittorrent(path: str, username: str, password: str) -> None:
    """Upload a downloaded torrent file to the local qBittorrent Web UI."""
    try:
        async with httpx.AsyncClient(base_url=QBITTORRENT_URL, timeout=HTTP_TIMEOUT) as client:
            login = await client.post(
                "/api/v2/auth/login",
                data={"username": username, "password": password},
            )
            if login.status_code in (401, 403):
                raise QbittorrentAuthenticationError(
                    "qBittorrent rejected the credentials"
                )
            login.raise_for_status()
            login_body = login.text.strip().lower()
            if login_body and login_body not in {"ok", "ok."}:
                raise QbittorrentAuthenticationError("qBittorrent rejected the credentials")

            torrent_data = await asyncio.to_thread(Path(path).read_bytes)
            response = await client.post(
                "/api/v2/torrents/add",
                files={
                    "torrents": (
                        Path(path).name,
                        torrent_data,
                        "application/x-bittorrent",
                    )
                },
            )
            response.raise_for_status()
            if response.text.strip().lower() == "fails.":
                raise QbittorrentError("qBittorrent could not add the torrent")
    except QbittorrentError:
        raise
    except (httpx.HTTPError, OSError) as ex:
        raise QbittorrentError(f"Could not add torrent to qBittorrent: {ex}") from ex


class NcoreService:
    """Holds a single logged-in ncoreparser session shared by all callers."""

    def __init__(self, settings_store):
        self._settings_store = settings_store
        self._client = None
        self._logged_in = False
        self._login_lock = asyncio.Lock()
        # Password set via the API for this run only; the settings store is
        # never given it, so it does not get written to settings.json
        self._session_password = None

    # -- credentials ---------------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        settings = self._settings_store.get_all()
        username = str(settings.get("ncore_username") or "").strip()
        password = self._session_password or str(settings.get("ncore_password") or "")
        return username, password

    def is_configured(self) -> bool:
        username, password = self._credentials()
        return bool(username and password)

    def is_logged_in(self) -> bool:
        return self._logged_in

    def _ensure_download_dir(self) -> str:
        path = self._settings_store.get("ncore_download_dir")
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    # -- session handling ----------------------------------------------------

    async def _get_client(self) -> AsyncClient:
        username, password = self._credentials()
        if not username or not password:
            raise NcoreNotConfigured(
                "Set ncore_username and ncore_password in the settings first."
            )
        async with self._login_lock:
            if self._client is None:
                self._client = AsyncClient(timeout=HTTP_TIMEOUT)
            if not self._logged_in:
                await self._client.login(username, password)
                self._logged_in = True
                logger.info("Logged in to nCore as %s", username)
        return self._client

    async def _invalidate(self):
        self._logged_in = False

    async def login(self, username: str | None = None, password: str | None = None) -> dict:
        """Login with the given or the stored credentials.

        The username is persisted to settings; the password is kept in memory
        for this process run only (provide it via NCORE_PASSWORD env for
        restarts).
        """
        if username is not None:
            self._settings_store.update({"ncore_username": username})
        if password is not None:
            self._session_password = password
        # Force a fresh login attempt even if we think we are logged in
        await self._invalidate()
        await self._get_client()
        return {"status": "ok", "message": f"Logged in to nCore as {self._credentials()[0]}"}

    async def logout(self) -> dict:
        async with self._login_lock:
            self._logged_in = False
            self._session_password = None
            if self._client is not None:
                await self._client.logout()
                self._client = None
        return {"status": "ok", "message": "Logged out from nCore"}

    async def status(self) -> dict:
        return {
            "configured": self.is_configured(),
            "logged_in": self._logged_in,
            "download_dir": self._settings_store.get("ncore_download_dir"),
            "password_source": "session" if self._session_password else (
                "env" if self._settings_store.get("ncore_password") else "none"
            ),
        }

    # -- operations -----------------------------------------------------------

    async def _run_with_relogin(self, operation):
        client = await self._get_client()
        try:
            return await operation(client)
        except NcoreConnectionError as ex:
            # check_login raises this when the stored session died; retry once
            if not self._logged_in or "Cannot login to tracker" not in str(ex):
                raise
            await self._invalidate()
            client = await self._get_client()
            return await operation(client)

    async def search(
        self,
        pattern: str,
        type: str = "all_own",
        where: str = "name",
        sort_by: str = "upload",
        sort_order: str = "DESC",
        page: int = 1,
    ) -> dict:
        def pick(enum_cls, value):
            try:
                return enum_cls(value)
            except ValueError:
                try:
                    return enum_cls[str(value).upper()]
                except KeyError:
                    raise NcoreParserError(
                        f"Invalid search parameter: '{value}' is not a {enum_cls.__name__}"
                    )
        type_param = pick(SearchParamType, type)
        where_param = pick(SearchParamWhere, where)
        sort_param = pick(ParamSort, sort_by)
        order_param = pick(ParamSeq, sort_order)

        result = await self._run_with_relogin(
            lambda client: client.search(
                pattern=pattern,
                type=type_param,
                where=where_param,
                sort_by=sort_param,
                sort_order=order_param,
                page=page,
            )
        )
        torrents = []
        for torrent in result.torrents:
            item = {}
            for field in TORRENT_FIELDS:
                if field in torrent.keys():
                    item[field] = str(torrent[field]) if field == "size" else torrent[field]
            item["url"] = torrent["url"]
            torrents.append(item)
        return {
            "torrents": torrents,
            "num_of_pages": result.num_of_pages,
            "page": page,
        }

    async def get_torrent(self, torrent_id: str) -> dict:
        torrent = await self._run_with_relogin(
            lambda client: client.get_torrent(torrent_id)
        )
        details = {}
        for field in TORRENT_FIELDS:
            if field in torrent.keys():
                details[field] = str(torrent[field]) if field == "size" else torrent[field]
        details["url"] = torrent["url"]
        return details

    async def download(self, torrent_id: str, override: bool = False) -> dict:
        """Download a .torrent file and add it to qBittorrent."""
        settings = self._settings_store.get_all()
        qbt_username = str(settings.get("qbt_username") or "").strip()
        qbt_password = str(settings.get("qbt_password") or "")
        if not qbt_username or not qbt_password:
            raise QbittorrentNotConfigured(
                "Set QBT_USERNAME and QBT_PASSWORD in the environment first."
            )

        download_dir = self._ensure_download_dir()
        file_path = await self._run_with_relogin(
            lambda client: self._download_one(client, torrent_id, download_dir, override)
        )
        await add_torrent_to_qbittorrent(file_path, qbt_username, qbt_password)
        return {
            "status": "ok",
            "message": f"Torrent saved and added to qBittorrent: {file_path}",
            "path": file_path,
            "download_dir": download_dir,
            "added_to_qbittorrent": True,
        }

    async def _download_one(self, client: AsyncClient, torrent_id: str, path: str, override: bool) -> str:
        torrent = await client.get_torrent(torrent_id)
        return await client.download(torrent, path, override=override)
