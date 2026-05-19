from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QStandardPaths

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


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = app_data_dir() / "thumb_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_extension(path: Path) -> str:
    return path.suffix.lower()


def is_supported_media(path: Path) -> bool:
    ext = normalize_extension(path)
    return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS or ext in MODEL_EXTENSIONS


def is_drive_root(path: Path) -> bool:
    return bool(path.drive and path.root and path.parent == path)


def media_kind_for_path(path: Path) -> str:
    ext = normalize_extension(path)
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in MODEL_EXTENSIONS:
        return "model"
    return "image"


def cache_key(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_type_label(item: MediaItem) -> str:
    if item.is_sequence and item.sequence:
        return f"Sequence {item.extension} [{item.sequence.frame_range_label}]"
    if item.is_video:
        return f"Video {item.extension}"
    if item.is_model:
        return f"Model {item.extension}"
    return f"Image {item.extension}"


def open_in_explorer(path: Path) -> None:
    try:
        subprocess.Popen(["explorer", "/select,", os.fspath(path)])
    except OSError:
        subprocess.Popen(["explorer", os.fspath(path.parent)])


def open_folder_in_explorer(path: Path) -> None:
    subprocess.Popen(["explorer", os.fspath(path)])


def find_windows_photo_viewer() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Windows Photo Viewer" / "PhotoViewer.dll",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Windows Photo Viewer" / "PhotoViewer.dll",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def open_image_in_default_viewer(path: Path) -> bool:
    photo_viewer = find_windows_photo_viewer()
    if photo_viewer is not None:
        try:
            process = subprocess.Popen(
                [
                    "rundll32.exe",
                    f"{os.fspath(photo_viewer)},ImageView_Fullscreen",
                    os.fspath(path),
                ]
            )
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                return True
        except OSError:
            pass

    if hasattr(os, "startfile"):
        try:
            os.startfile(os.fspath(path))
            return True
        except OSError:
            pass

    try:
        subprocess.Popen(["explorer", os.fspath(path)])
        return True
    except OSError:
        return False


def find_vlc_executable() -> Path | None:
    path = shutil.which("vlc")
    if path:
        return Path(path)

    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "VideoLAN" / "VLC" / "vlc.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "VideoLAN" / "VLC" / "vlc.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def open_video_in_vlc(path: Path) -> bool:
    vlc = find_vlc_executable()
    if vlc is None:
        return False
    subprocess.Popen([os.fspath(vlc), os.fspath(path)])
    return True


def open_fbx_in_viewer(path: Path) -> str | None:
    if hasattr(os, "startfile"):
        try:
            os.startfile(os.fspath(path))
            return "the default FBX app"
        except OSError:
            return None
    return None
