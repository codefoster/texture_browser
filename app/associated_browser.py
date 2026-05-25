from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.models import MediaItem
from app.thumbnail_grid import ThumbnailGrid
from app.thumbnailer import ThumbnailWorker
from app.utils import scale_px
from app.viewer import ViewerWindow
from app.workflow_filter import workflow_filter_predicate


class AssociatedBrowserDialog(QDialog):
    def __init__(
        self,
        items: list[MediaItem],
        current_index: int,
        thumbnail_size: int,
        parent: QWidget | None = None,
        window_title: str = "Associated Textures",
        count_label: str = "associated texture(s)",
        workflow_text: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(scale_px(920, self), scale_px(620, self))

        self.items = items
        self.count_label = count_label
        self.workflow_text = workflow_text
        self.current_index = max(0, min(current_index, len(items) - 1)) if items else 0
        self.thumbnail_size = thumbnail_size
        self.thumbnail_pool = QThreadPool(self)
        self.thumbnail_pool.setMaxThreadCount(4)
        self._thumb_jobs: set[tuple[str, int]] = set()
        self._selection_applied = False

        self.title_label = QLabel(f"{len(items)} {count_label}")
        self.workflow_filter_checkbox = QCheckBox("Workflow")
        self.workflow_filter_checkbox.setEnabled(workflow_filter_predicate(workflow_text) is not None)
        self.workflow_filter_checkbox.toggled.connect(self.apply_workflow_filter)
        self.grid = ThumbnailGrid()
        self.grid.set_thumbnail_size(thumbnail_size)
        self.grid.itemActivated.connect(self.open_viewer)
        self.grid.thumbnailRequested.connect(self.request_thumbnail)
        self.grid.visibleRangeChanged.connect(self.request_visible_thumbnails)
        self.grid.populationProgress.connect(lambda *_args: self._population_updated())
        self.grid.populationFinished.connect(lambda _count: self._population_updated())

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.workflow_filter_checkbox)
        layout.addLayout(header)
        layout.addWidget(self.grid, 1)

        self.grid.set_items(items)
        QTimer.singleShot(0, self.request_visible_thumbnails)

    def apply_workflow_filter(self, checked: bool) -> None:
        predicate = workflow_filter_predicate(self.workflow_text) if checked else None
        self.grid.apply_filter("", "", predicate)
        self._update_count_label()
        self.request_visible_thumbnails()

    def request_visible_thumbnails(self) -> None:
        for item in self.grid.visible_items():
            self.grid.thumbnailRequested.emit(item)

    def request_thumbnail(self, item: MediaItem) -> None:
        path_key = str(item.preview_path)
        key = (path_key, self.thumbnail_size)
        if key in self._thumb_jobs:
            return
        self._thumb_jobs.add(key)
        worker = ThumbnailWorker(item, self.thumbnail_size, 0)
        worker.signals.ready.connect(self._thumbnail_ready)
        self.thumbnail_pool.start(worker)

    def _thumbnail_ready(self, generation: int, path_key: str, size: int, pixmap) -> None:
        self._thumb_jobs.discard((path_key, size))
        if size != self.thumbnail_size:
            return
        self.grid.set_thumbnail(path_key, pixmap)
        if self.thumbnail_pool.activeThreadCount() < 2:
            self.request_visible_thumbnails()

    def open_viewer(self, item: MediaItem) -> None:
        items = self.grid.filtered_items()
        current_index = 0
        for index, media_item in enumerate(items):
            if media_item.preview_path == item.preview_path and media_item.display_name == item.display_name:
                current_index = index
                break
        viewer = ViewerWindow(items, current_index, self)
        viewer.exec()

    def _select_initial_item(self) -> None:
        if self._selection_applied:
            return
        if self.current_index >= self.grid.count():
            return

        item = self.grid.item(self.current_index)
        if item is None:
            return

        self.grid.setCurrentItem(item)
        self.grid.scrollToItem(item)
        self._selection_applied = True

    def _population_updated(self) -> None:
        self._update_count_label()
        self._select_initial_item()

    def _update_count_label(self) -> None:
        if self.workflow_filter_checkbox.isChecked():
            self.title_label.setText(f"{self.grid.visible_count()} of {len(self.items)} {self.count_label}")
            return
        self.title_label.setText(f"{len(self.items)} {self.count_label}")
