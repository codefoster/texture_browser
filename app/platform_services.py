"""Platform-specific handoffs to the file manager and external apps.

All shell-outs and default-app launches live here, dispatched on
``sys.platform``. Every function is exception-safe: failures return
False/None instead of raising, so UI slots can report them gracefully.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def file_manager_name() -> str:
    if sys.platform == "win32":
        return "Explorer"
    if sys.platform == "darwin":
        return "Finder"
    return "File Manager"


def open_folder(path: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(path)))


def _reveal_via_dbus(path: Path) -> bool:
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:
        return False
    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        interface = QDBusInterface(
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            bus,
        )
        if not interface.isValid():
            return False
        url = QUrl.fromLocalFile(os.fspath(path)).toString()
        reply = interface.call("ShowItems", [url], "")
        return reply.errorName() == ""
    except Exception:
        return False


def reveal_in_file_manager(path: Path) -> bool:
    if sys.platform == "win32":
        try:
            subprocess.Popen(["explorer", "/select,", os.fspath(path)])
            return True
        except OSError:
            return open_folder(path.parent)
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-R", os.fspath(path)])
            return True
        except OSError:
            return open_folder(path.parent)
    if _reveal_via_dbus(path):
        return True
    return open_folder(path.parent)


def open_with_default_app(path: Path) -> bool:
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(os.fspath(path))
            return True
        except OSError:
            pass
    elif sys.platform == "darwin":
        try:
            subprocess.Popen(["open", os.fspath(path)])
            return True
        except OSError:
            pass
    else:
        try:
            subprocess.Popen(["xdg-open", os.fspath(path)])
            return True
        except OSError:
            pass
    return QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(path)))


def find_vlc_command() -> list[str] | None:
    path = shutil.which("vlc")
    if path:
        return [path]

    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "VideoLAN" / "VLC" / "vlc.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "VideoLAN" / "VLC" / "vlc.exe",
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/VLC.app/Contents/MacOS/VLC"),
            Path.home() / "Applications" / "VLC.app" / "Contents" / "MacOS" / "VLC",
        ]
    else:
        candidates = [
            Path("/usr/bin/vlc"),
            Path("/usr/local/bin/vlc"),
            Path("/snap/bin/vlc"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return [os.fspath(candidate)]

    if sys.platform not in ("win32", "darwin") and shutil.which("flatpak"):
        try:
            result = subprocess.run(
                ["flatpak", "info", "org.videolan.VLC"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["flatpak", "run", "org.videolan.VLC"]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def open_video_in_vlc(path: Path) -> bool:
    command = find_vlc_command()
    if command is None:
        return False
    try:
        subprocess.Popen(command + [os.fspath(path)])
        return True
    except OSError:
        return False


def open_model_in_viewer(path: Path) -> str | None:
    if open_with_default_app(path):
        return "the default FBX app"
    return None


def vlc_install_hint() -> str:
    if sys.platform == "win32":
        return "Install VLC or add vlc.exe to your PATH."
    if sys.platform == "darwin":
        return "Install VLC into /Applications."
    return "Install VLC via your package manager, snap, or flatpak."


def fbx_handler_hint() -> str:
    if sys.platform == "win32":
        return "Install Blender or set a default app for .fbx files."
    if sys.platform == "darwin":
        return "Install Blender or choose a default app via Get Info > Open With."
    return "Install Blender or set a default application for .fbx files in your desktop environment."
