from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.models import THUMBNAIL_DIMENSIONS, MediaItem, ThumbnailSize
from app.sequence_detector import build_media_items
from app.thumbnailer import load_or_create_thumbnail
from app.utils import ensure_library_cache, is_cache_folder, is_supported_media


class CacheWorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)


class CacheWorker(QRunnable):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.signals = CacheWorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            ensure_library_cache(self.root)
            cached = 0
            size = THUMBNAIL_DIMENSIONS[ThumbnailSize.MEDIUM]
            for dirpath, dirnames, filenames in os.walk(self.root):
                if self._cancelled:
                    self.signals.progress.emit("Cache canceled")
                    self.signals.finished.emit(cached)
                    return

                dirnames[:] = [name for name in dirnames if not is_cache_folder(Path(name))]
                directory = Path(dirpath)
                paths: list[Path] = []
                for filename in filenames:
                    if self._cancelled:
                        self.signals.progress.emit("Cache canceled")
                        self.signals.finished.emit(cached)
                        return
                    path = directory / filename
                    if is_supported_media(path):
                        paths.append(path)
                if not paths:
                    continue

                items = build_media_items(paths)
                for item in items:
                    if self._cancelled:
                        self.signals.progress.emit("Cache canceled")
                        self.signals.finished.emit(cached)
                        return
                    if item.is_model or item.is_video:
                        continue
                    self._cache_item(item, size)
                    cached += 1
                    if cached % 25 == 0:
                        self.signals.progress.emit(f"Caching medium thumbnails... {cached} items prepared")

            self.signals.finished.emit(cached)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))

    def _cache_item(self, item: MediaItem, size: int) -> None:
        load_or_create_thumbnail(item, size)
