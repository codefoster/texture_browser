from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from app.media_dimensions import media_dimensions


class SizeFilterWorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(int, dict, list)
    error = Signal(int, str)


class SizeFilterWorker(QRunnable):
    def __init__(self, token: int, items: list) -> None:
        super().__init__()
        self.token = token
        self.items = items
        self.signals = SizeFilterWorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            dimensions_by_path: dict[str, str] = {}
            failed_paths: list[str] = []
            total = len(self.items)
            for index, item in enumerate(self.items, start=1):
                if self._cancelled:
                    return
                dimensions = media_dimensions(item.preview_path)
                if dimensions is None:
                    failed_paths.append(str(item.preview_path))
                else:
                    dimensions_by_path[str(item.preview_path)] = f"{dimensions[0]}x{dimensions[1]}"
                if index % 250 == 0:
                    self.signals.progress.emit(f"Reading image sizes... {index}/{total}")
            self.signals.finished.emit(self.token, dimensions_by_path, failed_paths)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(self.token, str(exc))
