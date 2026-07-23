from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.models import THUMBNAIL_DIMENSIONS, MediaItem, ThumbnailSize
from app.sequence_detector import build_media_items
from app.thumbnailer import load_or_create_thumbnail, rebuild_library_manifest
from app.utils import ensure_library_cache, is_cache_folder, is_supported_media, scale_px


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
            size = scale_px(THUMBNAIL_DIMENSIONS[ThumbnailSize.MEDIUM])
            items_to_cache: list[MediaItem] = []
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
                    items_to_cache.append(item)

            if not items_to_cache:
                self.signals.finished.emit(0)
                return

            max_workers = min(4, max(2, (os.cpu_count() or 4) // 2))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                item_iterator = iter(items_to_cache)
                pending = {}

                def fill_queue() -> None:
                    while len(pending) < max_workers * 2:
                        try:
                            item = next(item_iterator)
                        except StopIteration:
                            break
                        pending[executor.submit(self._cache_item, item, size)] = item

                fill_queue()
                while pending:
                    if self._cancelled:
                        self.signals.progress.emit("Cache canceled")
                        for future in pending:
                            future.cancel()
                        self.signals.finished.emit(cached)
                        return

                    done, _ = wait(pending.keys(), timeout=0.1, return_when=FIRST_COMPLETED)
                    if not done:
                        continue
                    for future in done:
                        future.result()
                        pending.pop(future, None)
                        cached += 1
                        if cached % 50 == 0:
                            self.signals.progress.emit(
                                f"Caching medium thumbnails... {cached}/{len(items_to_cache)} items prepared"
                            )
                    fill_queue()

            rebuild_library_manifest(self.root, items_to_cache, [size])

            self.signals.finished.emit(cached)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))

    def _cache_item(self, item: MediaItem, size: int) -> None:
        load_or_create_thumbnail(item, size)
