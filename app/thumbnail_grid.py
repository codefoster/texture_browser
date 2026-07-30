from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import QEvent, QMimeData, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QWidget,
)

from app.models import MediaItem
from app.thumbnailer import build_placeholder
from app.platform_services import file_manager_name, reveal_in_file_manager
from app.utils import format_type_label, scale_px


class ThumbnailGrid(QListWidget):
    itemActivated = Signal(MediaItem)
    thumbnailRequested = Signal(MediaItem)
    visibleRangeChanged = Signal()
    populationFinished = Signal(int)
    populationProgress = Signal(int, int)
    filesDropped = Signal(list)
    associatedRequested = Signal(MediaItem)
    guessRequested = Signal(MediaItem)
    materialSetRequested = Signal(MediaItem)
    validationRequested = Signal(MediaItem)
    channelInspectorRequested = Signal(MediaItem)
    tagFileRequested = Signal(MediaItem)
    tagMaterialSetRequested = Signal(MediaItem)
    removeTagRequested = Signal(MediaItem)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[MediaItem] = []
        self._item_map: dict[Path, QListWidgetItem] = {}
        self._thumb_size = 160
        self._loaded_paths: set[Path] = set()
        self._prefetch_chunk_size = 100
        self._populate_batch_size = 1000
        self._active_populate_batch_size = self._populate_batch_size
        self._pending_items: list[MediaItem] = []
        self._added_count = 0
        self._placeholder_icons: dict[tuple[str, int, bool], QIcon] = {}
        self._filter_query = ""
        self._filter_groups: list[list[str]] = []
        self._extension_filters: set[str] = set()
        self._extra_filter = None
        self._visible_count = 0
        self._visible_timer = QTimer(self)
        self._visible_timer.setSingleShot(True)
        self._visible_timer.setInterval(60)
        self._visible_timer.timeout.connect(self._emit_visible_range_changed)
        self._populate_timer = QTimer(self)
        self._populate_timer.setSingleShot(True)
        self._populate_timer.setInterval(0)
        self._populate_timer.timeout.connect(self._populate_next_batch)

        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(scale_px(8, self))
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideNone)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.verticalScrollBar().valueChanged.connect(self.schedule_visible_refresh)
        self.horizontalScrollBar().valueChanged.connect(self.schedule_visible_refresh)
        self.viewport().installEventFilter(self)
        self._apply_size()

    def set_thumbnail_size(self, size: int) -> None:
        self._thumb_size = size
        self._loaded_paths.clear()
        self._placeholder_icons.clear()
        self._apply_size()
        size_hint = self._item_size_hint()
        self.setUpdatesEnabled(False)
        try:
            for row in range(self.count()):
                item = self.item(row)
                media_item = item.data(Qt.UserRole)
                item.setSizeHint(size_hint)
                item.setIcon(self._placeholder_icon(media_item))
        finally:
            self.setUpdatesEnabled(True)
        self.doItemsLayout()
        self.updateGeometries()
        self.viewport().update()
        self.schedule_visible_refresh()

    def set_items(self, items: list[MediaItem], batch_size: int | None = None) -> None:
        self.reset_grid_state()
        self._active_populate_batch_size = batch_size or self._populate_batch_size
        self._items = items
        self._pending_items = list(items)
        self._added_count = 0
        self._visible_count = 0
        self._populate_timer.start()

    def append_items(self, items: list[MediaItem]) -> None:
        if not items:
            return
        self._items.extend(items)
        self._pending_items.extend(items)
        if not self._populate_timer.isActive():
            self._populate_timer.start()

    def reset_grid_state(self) -> None:
        self._populate_timer.stop()
        self._visible_timer.stop()
        self.clear()
        self._items = []
        self._item_map.clear()
        self._loaded_paths.clear()
        self._pending_items = []
        self._added_count = 0
        self._visible_count = 0
        self._active_populate_batch_size = self._populate_batch_size

    def apply_filter(self, text: str, extension_filter: str = "", extra_filter=None) -> None:
        query = text.strip().lower()
        self._filter_query = query
        self._filter_groups = self._parse_filter_groups(query)
        self._extension_filters = self._parse_extension_filters(extension_filter)
        self._extra_filter = extra_filter
        visible_count = 0
        self.setUpdatesEnabled(False)
        try:
            for row in range(self.count()):
                item = self.item(row)
                media_item = item.data(Qt.UserRole)
                hidden = self._is_hidden_by_filter(media_item)
                if item.isHidden() != hidden:
                    item.setHidden(hidden)
                if not hidden:
                    visible_count += 1
        finally:
            self.setUpdatesEnabled(True)
        self._visible_count = visible_count
        self.schedule_visible_refresh()

    def set_thumbnail(self, path_key: str, pixmap) -> None:
        path = Path(path_key)
        item = self._item_map.get(path)
        if item is None:
            return
        item.setIcon(QIcon(pixmap))
        self._loaded_paths.add(path)

    def visible_items(self) -> list[MediaItem]:
        if self.count() == 0:
            return []

        return self._collect_unloaded_visible_items()

    def prefetch_items(self) -> list[MediaItem]:
        if self.count() == 0:
            return []

        visible_rows = self._visible_row_indexes()
        if not visible_rows:
            return []
        bottom_row = visible_rows[-1]
        next_start = bottom_row + 1
        next_end = min(self.count() - 1, bottom_row + self._prefetch_chunk_size)
        if next_start <= next_end:
            return self._collect_unloaded_items(next_start, next_end)
        return []

    def _apply_size(self) -> None:
        size_hint = self._item_size_hint()
        self.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.setGridSize(size_hint)

    def _item_size_hint(self) -> QSize:
        tiny_limit = scale_px(72, self)
        small_limit = scale_px(112, self)
        medium_limit = scale_px(160, self)
        if self._thumb_size <= tiny_limit:
            text_width = scale_px(28, self)
            text_height = scale_px(74, self)
        elif self._thumb_size <= small_limit:
            text_width = scale_px(28, self)
            text_height = scale_px(78, self)
        elif self._thumb_size <= medium_limit:
            text_width = scale_px(32, self)
            text_height = scale_px(84, self)
        else:
            text_width = scale_px(40, self)
            text_height = scale_px(92, self)
        return QSize(self._thumb_size + text_width, self._thumb_size + text_height)

    def schedule_visible_refresh(self) -> None:
        self._visible_timer.start()

    def visible_count(self) -> int:
        return self._visible_count

    def total_count(self) -> int:
        return len(self._items)

    def filtered_items(self) -> list[MediaItem]:
        items: list[MediaItem] = []
        for row in range(self.count()):
            item = self.item(row)
            if item.isHidden():
                continue
            items.append(item.data(Qt.UserRole))
        return items

    def selected_media_items(self) -> list[MediaItem]:
        items: list[MediaItem] = []
        seen: set[tuple[Path, str]] = set()
        for widget_item in self.selectedItems():
            media_item = widget_item.data(Qt.UserRole)
            if media_item is None:
                continue
            key = (media_item.preview_path, media_item.display_name)
            if key in seen:
                continue
            seen.add(key)
            items.append(media_item)
        return items

    def index_of_item(self, target: MediaItem) -> int:
        filtered = self.filtered_items()
        for index, item in enumerate(filtered):
            if item.preview_path == target.preview_path and item.display_name == target.display_name:
                return index
        return -1

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        mime_data = QMimeData()
        paths: list[Path] = []
        seen: set[Path] = set()
        for item in items:
            media_item = item.data(Qt.UserRole)
            if media_item is None:
                continue
            item_paths = media_item.sequence.frame_paths if media_item.sequence else [media_item.preview_path]
            for path in item_paths:
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                paths.append(resolved)
        mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        return mime_data

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport() and event.type() in {QEvent.Resize, QEvent.Paint, QEvent.Wheel}:
            self.schedule_visible_refresh()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.schedule_visible_refresh()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        media_item = item.data(Qt.UserRole)
        self.itemActivated.emit(media_item)

    def _show_context_menu(self, position) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        media_item = item.data(Qt.UserRole)

        menu = QMenu(self)
        associated_action = QAction("Select workflow", self)
        guess_action = QAction("Guess", self)
        material_set_action = QAction("Material set", self)
        validate_action = QAction("Validate texture set", self)
        channel_action = QAction("Channel inspector", self)
        tag_file_action = QAction("Tag file...", self)
        tag_material_set_action = QAction("Tag material set...", self)
        remove_tag_action = QAction("Remove tag...", self)
        open_action = QAction(f"Reveal in {file_manager_name()}", self)
        copy_file_action = QAction("Copy file path", self)
        copy_folder_action = QAction("Copy folder path", self)

        associated_action.triggered.connect(lambda: self.associatedRequested.emit(media_item))
        guess_action.triggered.connect(lambda: self.guessRequested.emit(media_item))
        material_set_action.triggered.connect(lambda: self.materialSetRequested.emit(media_item))
        validate_action.triggered.connect(lambda: self.validationRequested.emit(media_item))
        channel_action.triggered.connect(lambda: self.channelInspectorRequested.emit(media_item))
        tag_file_action.triggered.connect(lambda: self.tagFileRequested.emit(media_item))
        tag_material_set_action.triggered.connect(lambda: self.tagMaterialSetRequested.emit(media_item))
        remove_tag_action.triggered.connect(lambda: self.removeTagRequested.emit(media_item))
        open_action.triggered.connect(lambda: reveal_in_file_manager(media_item.preview_path))
        copy_file_action.triggered.connect(
            lambda: QApplication.clipboard().setText(str(media_item.preview_path))
        )
        copy_folder_action.triggered.connect(
            lambda: QApplication.clipboard().setText(str(media_item.folder))
        )

        menu.addAction(associated_action)
        menu.addAction(guess_action)
        menu.addAction(material_set_action)
        menu.addAction(validate_action)
        menu.addAction(channel_action)
        menu.addSeparator()
        menu.addAction(tag_file_action)
        menu.addAction(tag_material_set_action)
        menu.addAction(remove_tag_action)
        menu.addSeparator()
        menu.addAction(open_action)
        menu.addAction(copy_file_action)
        menu.addAction(copy_folder_action)
        menu.exec(self.mapToGlobal(position))

    def _emit_visible_range_changed(self) -> None:
        self.visibleRangeChanged.emit()

    def _populate_next_batch(self) -> None:
        if not self._pending_items:
            self.populationFinished.emit(self._visible_count)
            self.schedule_visible_refresh()
            return

        batch_size = self._active_populate_batch_size
        batch = self._pending_items[:batch_size]
        del self._pending_items[:batch_size]

        size_hint = self._item_size_hint()
        self.setUpdatesEnabled(False)
        try:
            for media_item in batch:
                widget_item = QListWidgetItem()
                widget_item.setText(self._display_label(media_item.display_name))
                widget_item.setData(Qt.UserRole, media_item)
                widget_item.setToolTip(f"{media_item.display_name}\n{format_type_label(media_item)}")
                widget_item.setSizeHint(size_hint)
                widget_item.setIcon(self._placeholder_icon(media_item))
                hidden = self._is_hidden_by_filter(media_item)
                self.addItem(widget_item)
                widget_item.setHidden(hidden)
                if not hidden:
                    self._visible_count += 1
                self._item_map[media_item.preview_path] = widget_item
        finally:
            self.setUpdatesEnabled(True)

        self._added_count += len(batch)
        self.populationProgress.emit(self._added_count, len(self._items))
        self._populate_timer.start()

    def _placeholder_icon(self, media_item: MediaItem) -> QIcon:
        key = (media_item.extension or "file", self._thumb_size, media_item.is_video)
        icon = self._placeholder_icons.get(key)
        if icon is None:
            icon = QIcon(build_placeholder(key[0], key[1], key[2]))
            self._placeholder_icons[key] = icon
        return icon

    def _visible_row_indexes(self) -> list[int]:
        viewport_rect = self.viewport().rect()
        rows: list[int] = []
        for row in range(self.count()):
            item = self.item(row)
            if item.isHidden():
                continue
            item_rect = self.visualItemRect(item)
            if item_rect.isValid() and item_rect.intersects(viewport_rect):
                rows.append(row)
        return rows

    def _collect_unloaded_visible_items(self) -> list[MediaItem]:
        items: list[MediaItem] = []
        for row in self._visible_row_indexes():
            item = self.item(row)
            media_item = item.data(Qt.UserRole)
            if media_item.preview_path in self._loaded_paths:
                continue
            items.append(media_item)
        return items

    def _collect_unloaded_items(self, start_row: int, end_row: int) -> list[MediaItem]:
        items: list[MediaItem] = []
        for row in range(start_row, end_row + 1):
            item = self.item(row)
            if item.isHidden():
                continue
            media_item = item.data(Qt.UserRole)
            if media_item.preview_path in self._loaded_paths:
                continue
            items.append(media_item)
        return items

    def _is_hidden_by_filter(self, media_item: MediaItem) -> bool:
        filename_search_text = self._filename_search_text(media_item)
        matches_query = self._matches_filter_groups(filename_search_text)
        if self._extension_filters:
            extension_hidden = media_item.extension not in self._extension_filters
        else:
            extension_hidden = media_item.is_video or media_item.is_model
        extra_hidden = self._extra_filter is not None and not self._extra_filter(media_item)
        return (not matches_query) or extension_hidden or extra_hidden

    def _filename_search_text(self, media_item: MediaItem) -> str:
        parts = [media_item.display_name, media_item.preview_path.name]
        if media_item.sequence:
            parts.append(media_item.sequence.pattern_name)
        return " ".join(part.lower() for part in parts if part)

    def _parse_filter_groups(self, query: str) -> list[list[str]]:
        groups: list[list[str]] = []
        for raw_group in query.split(","):
            tokens = re.findall(r"[a-z0-9]+", raw_group.lower())
            if tokens:
                groups.append(tokens)
        return groups

    def _matches_filter_groups(self, filename_search_text: str) -> bool:
        if not self._filter_groups:
            return True
        for group in self._filter_groups:
            if all(token in filename_search_text for token in group):
                return True
        return False

    def _parse_extension_filters(self, text: str) -> set[str]:
        extensions: set[str] = set()
        for raw_part in text.lower().replace(",", " ").replace(";", " ").split():
            extension = raw_part.strip()
            if not extension:
                continue
            if not extension.startswith("."):
                extension = f".{extension}"
            extensions.add(extension)
        return extensions

    def _display_label(self, name: str) -> str:
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
        text = text.replace("_", "_ ").replace("-", "- ")
        text = re.sub(r"\s+", " ", text).strip()
        return text
