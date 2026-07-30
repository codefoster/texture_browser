"""Offscreen launch smoke test, run by CI on Windows/macOS/Linux.

Instantiates the real MainWindow under the offscreen Qt platform and
exercises the platform helpers. Exits nonzero on any failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.platform_services import (
    fbx_handler_hint,
    file_manager_name,
    find_vlc_command,
    vlc_install_hint,
)
from app.utils import is_drive_root, normalize_path_key


def check_platform_helpers() -> None:
    if sys.platform == "win32":
        assert is_drive_root(Path("C:\\")), "C:\\ should be a drive root"
        assert normalize_path_key(Path("C:\\Tex")) == normalize_path_key(Path("c:\\tex"))
    else:
        assert is_drive_root(Path("/")), "/ should be a drive root"
        assert is_drive_root(Path("/mnt/c")), "/mnt/c should be a drive root"
    assert not is_drive_root(Path.home()), "home dir must not be a drive root"

    assert file_manager_name()
    assert vlc_install_hint()
    assert fbx_handler_hint()
    find_vlc_command()  # must not raise, may be None


def check_window_launch() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()


def main() -> int:
    check_platform_helpers()
    check_window_launch()
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
