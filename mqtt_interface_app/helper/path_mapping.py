"""Container <-> host path mapping for the file browser and VLC.

When the app runs in Docker the media folder is mounted into the container
(e.g. `-v D:/Media:/media`), so the browser sees container paths while VLC
on the host needs the original host paths in its file:// URIs. The mapping
is a plain prefix swap driven by two settings:

- `media_root`: the folder as seen inside the container (browsable)
- `media_host_path`: the same folder as seen by the host (VLC); empty when
  the app runs directly on the host (no mapping, paths pass through)
"""
from pathlib import PurePosixPath, PureWindowsPath


def _is_windows_drive(path: str) -> bool:
    forward = str(path).replace("\\", "/")
    return len(forward) >= 2 and forward[1] == ":"


def _normalized_prefix(path: str) -> str:
    """Forward-slash form with any trailing separator stripped."""
    return str(path).replace("\\", "/").rstrip("/")


def map_path(path: str, source_root: str, target_root: str) -> str:
    """Rebase `path` from `source_root` onto `target_root`.

    Prefix matching is case-insensitive (Windows) and works across path
    styles (the two roots are usually on different OSes when in Docker).
    Returns `path` unchanged when the mapping is disabled (empty roots) or
    `path` does not sit under `source_root`. The result keeps the slash
    style both `Path` implementations accept: `D:/Videos/x.mkv` is valid on
    Windows, `/media/x.mkv` in the container.
    """
    if not path or not source_root or not target_root:
        return path
    source = _normalized_prefix(source_root)
    forward = str(path).replace("\\", "/")
    low, low_src = forward.lower(), source.lower()
    if low != low_src and not low.startswith(low_src + "/"):
        return path
    rel = forward[len(source):].lstrip("/")
    target = _normalized_prefix(target_root)
    if not rel:
        return target
    return f"{target}/{rel}"


def container_to_host(path: str, media_root: str, media_host_path: str) -> str:
    """Path as seen inside the container -> path VLC must open on the host."""
    return map_path(path, media_root, media_host_path)


def host_to_container(path: str, media_root: str, media_host_path: str) -> str:
    """Path VLC reports (playlist URI) -> browsable path inside the container."""
    return map_path(path, media_host_path, media_root)


def mapping_active(media_root: str, media_host_path: str) -> bool:
    return bool(media_root and media_host_path)


def file_name(path: str) -> str:
    """Basename that works for both Windows and POSIX style paths."""
    return str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def path_to_uri(path: str) -> str:
    """file:// URI for a path that may be a *host* path (e.g. 'D:/Media/x.mkv',
    'D:\\Media\\x.mkv' or a UNC path) even though this code may run on Linux."""
    text = str(path)
    forward = text.replace("\\", "/")
    # Windows drive path (D:/...) or UNC path (//server/share/...)
    if (len(forward) >= 2 and forward[1] == ":") or forward.startswith("//"):
        return PureWindowsPath(text).as_uri()
    return PurePosixPath(forward).as_uri()
