"""Browse local media files so the web UI can open them in VLC.

Browsing is restricted to a set of "allowed roots":
- the `media_root` setting,
- the nCore download directory,
- the folder of the media VLC is currently playing (via playlist.json).

When running in Docker, the browser works with container paths (the media
folder is volume-mounted at `media_root`) while VLC on the host needs the
original host path: `media_host_path` maps between the two.

The default listing starts in the current media's folder when VLC knows it,
falling back to `media_root`.
"""
import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Request

from helper.path_mapping import host_to_container, mapping_active

router = APIRouter(prefix="/api/v1/files", tags=["files"])

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".flv", ".ogv",
}
SUBTITLE_EXTENSIONS = {
    ".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx", ".sup", ".sbv",
}


def _leaf_uris(node: dict, found: list) -> list:
    """Recursively collect leaf playlist entries that have a uri."""
    for child in node.get("children", []):
        if "uri" in child:
            found.append(child)
        else:
            _leaf_uris(child, found)
    return found


def _unquote_file_uri(uri: str) -> str | None:
    """file:// URI -> plain host path (None for non-file URIs)."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    local = unquote(parsed.path)
    # Windows file URIs look like /C:/Users/...: strip the leading slash so
    # the path is a valid absolute Windows path
    if len(local) >= 3 and local[0] == "/" and local[2] == ":":
        local = local[1:]
    return local


def current_media_path(listener, settings_store=None) -> str | None:
    """Browsable container path of the media VLC currently plays.

    Derived from playlist.json (a host-side file path); mapped into the
    container via the media_root/media_host_path settings. Returns None when
    the path cannot be resolved or does not exist in the container.
    """
    try:
        result = listener.get_playlist()
    except Exception:
        return None
    if result.status != "ok" or not result.payload:
        return None
    leaves = _leaf_uris(result.payload, [])
    current = next((leaf for leaf in leaves if leaf.get("current") == "current"), None)
    if not current or not current.get("uri"):
        return None
    local = _unquote_file_uri(current["uri"])
    if not local:
        return None
    if settings_store is not None and mapping_active(
        settings_store.get("media_root"), settings_store.get("media_host_path")
    ):
        local = host_to_container(
            local, settings_store.get("media_root"), settings_store.get("media_host_path")
        )
    if not Path(local).exists():
        return None
    return local


def allowed_roots(settings_store, listener) -> list[Path]:
    """Directories the browser may enter (existing ones only, no duplicates)."""
    roots: list[Path] = []
    for raw in (
        settings_store.get("media_root"),
        settings_store.get("ncore_download_dir"),
        current_media_path(listener, settings_store),
    ):
        if not raw:
            continue
        root = Path(raw).resolve()
        if not root.exists():
            continue
        target = root if root.is_dir() else root.parent
        if target not in roots:
            roots.append(target)
    return roots


def _is_within(candidate: Path, roots: list[Path]) -> bool:
    for root in roots:
        if candidate == root or root in candidate.parents:
            return True
    return False


def _default_start_dir(roots: list[Path]) -> Path:
    # VLC's current folder first, then media_root
    return roots[2] if len(roots) > 2 else roots[0]


@router.get("/browser")
async def browse(request: Request, path: str | None = None):
    settings_store = request.app.state.settings_store
    listener = request.app.state.vlc_listener
    roots = await asyncio.to_thread(allowed_roots, settings_store, listener)

    if not roots:
        return {"path": None, "parent": None, "directories": [], "files": [],
                "message": "No accessible media folders (check the media_root setting and the Docker volume mount)"}

    if path:
        requested = Path(path).resolve()
        if not _is_within(requested, roots):
            return {"path": None, "parent": None, "directories": [], "files": [],
                    "message": "Folder is outside the allowed media folders"}
    else:
        requested = _default_start_dir(roots)

    if requested.is_file():
        requested = requested.parent

    if not requested.is_dir():
        return {"path": str(requested), "parent": None, "directories": [], "files": [],
                "message": "Folder not found"}

    directories = []
    files = []
    try:
        for entry in requested.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                directories.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                ext = entry.suffix.lower()
                kind = None
                if ext in VIDEO_EXTENSIONS:
                    kind = "video"
                elif ext in SUBTITLE_EXTENSIONS:
                    kind = "subtitle"
                if not kind:
                    continue
                try:
                    stat = entry.stat()
                    files.append({
                        "name": entry.name,
                        "path": str(entry),
                        "type": kind,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
                except OSError:
                    continue
    except PermissionError:
        return {"path": str(requested), "parent": None, "directories": [], "files": [],
                "message": "Permission denied"}

    directories.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())

    parent = None
    if requested != requested.parent and _is_within(requested.parent, roots):
        parent = str(requested.parent)

    return {
        "path": str(requested),
        "parent": str(parent) if parent else None,
        "directories": directories,
        "files": files,
    }
