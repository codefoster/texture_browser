from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QGuiApplication

from app.models import MediaItem

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".tga",
    ".psd",
    ".exr",
    ".hdr",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

MODEL_EXTENSIONS = {
    ".fbx",
}

LIBRARY_CACHE_DIRNAME = ".texturebrowser-cache"
LIBRARY_CACHE_MANIFEST = "index.json"
BASE_SCREEN_WIDTH = 1920
BASE_SCREEN_HEIGHT = 1080
BASE_DPI = 96.0

_manifest_lock = threading.RLock()


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ui_scale_factor(widget=None) -> float:
    screen = None
    if widget is not None:
        try:
            screen = widget.screen()
        except RuntimeError:
            screen = None
    if screen is None:
        app = QGuiApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
    if screen is None:
        return 1.0

    geometry = screen.availableGeometry()
    geometry_factor = min(
        geometry.width() / BASE_SCREEN_WIDTH,
        geometry.height() / BASE_SCREEN_HEIGHT,
    )
    dpi_factor = screen.logicalDotsPerInch() / BASE_DPI
    return max(1.0, min(2.0, max(geometry_factor, dpi_factor)))


def scale_px(value: int, widget=None, minimum: int = 1) -> int:
    return max(minimum, int(round(value * ui_scale_factor(widget))))


def cache_dir() -> Path:
    path = app_data_dir() / "thumb_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_cache_dir(root: Path) -> Path:
    return root / LIBRARY_CACHE_DIRNAME / "thumbs"


def library_cache_root(root: Path) -> Path:
    return root / LIBRARY_CACHE_DIRNAME


def library_manifest_path(root: Path) -> Path:
    return library_cache_root(root) / LIBRARY_CACHE_MANIFEST


def ensure_library_cache(root: Path) -> Path:
    cache_root = library_cache_root(root)
    thumbs_dir = cache_root / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    _hide_path_windows(cache_root)
    return thumbs_dir


def find_library_cache_root(path: Path) -> Path | None:
    start = path if path.is_dir() else path.parent
    for parent in [start, *start.parents]:
        cache_root = library_cache_root(parent)
        if cache_root.exists():
            return parent
    return None


def find_library_cache_dir(path: Path) -> Path | None:
    library_root = find_library_cache_root(path)
    if library_root is None:
        return None
    thumbs_dir = library_cache_dir(library_root)
    return thumbs_dir if thumbs_dir.exists() else None


def load_library_manifest(root: Path) -> dict:
    manifest_path = library_manifest_path(root)
    if not manifest_path.exists():
        return {"version": 1, "entries": {}}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "entries": {}}
    entries = payload.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    return {"version": 1, "entries": entries}


def save_library_manifest(root: Path, manifest: dict) -> None:
    manifest_path = library_manifest_path(root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "entries": manifest.get("entries", {}),
    }
    with _manifest_lock:
        temp_fd, temp_name = tempfile.mkstemp(
            prefix="texturebrowser-manifest-",
            suffix=".json",
            dir=str(manifest_path.parent),
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            os.replace(temp_name, manifest_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def normalize_extension(path: Path) -> str:
    return path.suffix.lower()


def is_supported_media(path: Path) -> bool:
    ext = normalize_extension(path)
    return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS or ext in MODEL_EXTENSIONS


def is_drive_root(path: Path) -> bool:
    """Heuristic guard against scanning a whole volume.

    True for filesystem roots ("C:\\", "/") and for direct children of the
    common POSIX mount parents ("/Volumes/T7", "/mnt/c", "/media/usb0",
    "/media/<user>/<volume>"). Deliberately not ``os.path.ismount`` — that
    would also block scanning legitimately mounted network libraries at
    their mount point.
    """
    resolved = path.resolve()
    if resolved.parent == resolved:
        return True
    if sys.platform == "win32":
        return False
    parent = resolved.parent
    if parent in (Path("/Volumes"), Path("/mnt"), Path("/media")):
        return True
    if parent.parent == Path("/media"):
        return True
    return False


def normalize_path_key(path: Path) -> str:
    """Stable string identity for a path, for cache/dedupe keys.

    Lowercases only on platforms whose default filesystems are
    case-insensitive; on Linux, distinct case means distinct paths.
    """
    text = str(path.resolve())
    if sys.platform in ("win32", "darwin"):
        return text.lower()
    return text


def media_kind_for_path(path: Path) -> str:
    ext = normalize_extension(path)
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in MODEL_EXTENSIONS:
        return "model"
    return "image"


def cache_key(path: Path, root: Path | None = None) -> str:
    stat = path.stat()
    resolved = path.resolve()
    if root is not None:
        try:
            identifier = resolved.relative_to(root.resolve())
        except ValueError:
            identifier = resolved
    else:
        identifier = resolved
    raw = f"{identifier}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_cache_folder(path: Path) -> bool:
    return path.name.lower() == LIBRARY_CACHE_DIRNAME.lower()


def format_type_label(item: MediaItem) -> str:
    if item.is_sequence and item.sequence:
        return f"Sequence {item.extension} [{item.sequence.frame_range_label}]"
    if item.is_video:
        return f"Video {item.extension}"
    if item.is_model:
        return f"Model {item.extension}"
    return f"Image {item.extension}"


def _hide_path_windows(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
    except (AttributeError, OSError):
        pass
