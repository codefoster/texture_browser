from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFileSystemModel,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSplitter,
    QStyle,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from app.utils import is_drive_root, scale_px


class StableFolderIconProvider(QFileIconProvider):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            self.setOption(QFileIconProvider.DontUseCustomDirectoryIcons)
        except AttributeError:
            pass

    def icon(self, info_or_type):  # type: ignore[override]
        if hasattr(info_or_type, "isDir") and info_or_type.isDir():
            return _folder_icon_for_path(Path(info_or_type.absoluteFilePath()))
        icon = super().icon(info_or_type)
        if not icon.isNull():
            return icon
        style = QApplication.style()
        if style is None:
            return icon
        return style.standardIcon(QStyle.SP_FileIcon)


def _folder_icon_for_path(path: Path):
    style = QApplication.style()
    if style is None:
        return None
    if is_drive_root(path):
        return style.standardIcon(QStyle.SP_DriveHDIcon)
    return style.standardIcon(QStyle.SP_DirIcon)


class FolderFileSystemModel(QFileSystemModel):
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        value = super().data(index, role)
        if role == Qt.DecorationRole and index.column() == 0:
            info = self.fileInfo(index)
            if info.isDir():
                icon = _folder_icon_for_path(Path(info.absoluteFilePath()))
                if icon is not None:
                    return icon
                return value
            try:
                if value is not None and not value.isNull():
                    return value
            except AttributeError:
                if value is not None:
                    return value
            style = QApplication.style()
            if style is None:
                return value
            return style.standardIcon(QStyle.SP_FileIcon)
        return value


class FolderBrowser(QWidget):
    folderSelected = Signal(Path)
    folderOpenRequested = Signal(Path)
    addFavoriteRequested = Signal(Path)
    removeFavoriteRequested = Signal(Path)
    favoriteSearchToggled = Signal(Path, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_folder: Path | None = None

        self.favorites_list = QListWidget()
        self.favorites_list.itemDoubleClicked.connect(self._on_favorite_activated)
        self.favorites_list.itemChanged.connect(self._on_favorite_changed)
        self.favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self._show_favorites_context_menu)

        self.favorites_label = QLabel("FAVORITES")
        self.favorites_label.setProperty("variant", "kicker")

        self.model = FolderFileSystemModel(self)
        self.model.setIconProvider(StableFolderIconProvider(self.model))
        self.model.setRootPath(QDir.rootPath())
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(scale_px(16, self))
        self.tree.setIconSize(QSize(scale_px(18, self), scale_px(18, self)))
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.tree.setHorizontalScrollMode(QTreeView.ScrollPerPixel)
        self.tree.setMinimumWidth(0)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree.doubleClicked.connect(self._on_tree_double_clicked)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)

        label_margin = scale_px(10, self)
        self.favorites_label.setContentsMargins(label_margin, scale_px(10, self), label_margin, scale_px(4, self))

        favorites_panel = QWidget()
        favorites_layout = QVBoxLayout(favorites_panel)
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        favorites_layout.setSpacing(0)
        favorites_layout.addWidget(self.favorites_label)
        favorites_layout.addWidget(self.favorites_list, 1)

        self.folders_label = QLabel("FOLDERS")
        self.folders_label.setProperty("variant", "kicker")
        self.folders_label.setContentsMargins(label_margin, scale_px(10, self), label_margin, scale_px(4, self))

        folders_panel = QWidget()
        folders_layout = QVBoxLayout(folders_panel)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.setSpacing(0)
        folders_layout.addWidget(self.folders_label)
        folders_layout.addWidget(self.tree, 1)

        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.addWidget(favorites_panel)
        self.vertical_splitter.addWidget(folders_panel)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setSizes([scale_px(180, self), scale_px(420, self)])
        self.vertical_splitter.setOpaqueResize(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.vertical_splitter, 1)

    def set_current_folder(self, folder: Path) -> None:
        self._current_folder = folder
        index = self.model.index(str(folder))
        if index.isValid():
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)

    def set_favorites(self, favorites: list[Path], enabled_favorites: set[Path] | None = None) -> None:
        self.favorites_list.blockSignals(True)
        self.favorites_list.clear()
        for path in favorites:
            item = QListWidgetItem(f"★ {path.name or str(path)}")
            item.setData(Qt.UserRole, path)
            item.setToolTip(str(path))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = True if enabled_favorites is None else path in enabled_favorites
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.favorites_list.addItem(item)
        self.favorites_list.blockSignals(False)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        path = Path(self.model.filePath(current))
        if path.exists():
            self._current_folder = path

    def _on_tree_double_clicked(self, index: QModelIndex) -> None:
        path = Path(self.model.filePath(index))
        if path.exists():
            self._current_folder = path
            self.folderSelected.emit(path)

    def _show_tree_context_menu(self, position: QPoint) -> None:
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        path = Path(self.model.filePath(index))
        if not path.exists():
            return
        menu = QMenu(self)
        add_favorite_action = QAction("Add to Favorites", self)
        add_favorite_action.triggered.connect(lambda checked=False, folder=path: self.addFavoriteRequested.emit(folder))
        menu.addAction(add_favorite_action)
        show_folder_action = QAction("Show Folder", self)
        show_folder_action.triggered.connect(lambda checked=False, folder=path: self.folderOpenRequested.emit(folder))
        menu.addAction(show_folder_action)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _show_favorites_context_menu(self, position: QPoint) -> None:
        item = self.favorites_list.itemAt(position)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if not isinstance(path, Path):
            return
        menu = QMenu(self)
        show_folder_action = QAction("Show Folder", self)
        show_folder_action.triggered.connect(lambda checked=False, folder=path: self.folderOpenRequested.emit(folder))
        menu.addAction(show_folder_action)
        remove_action = QAction("Remove from Favorites", self)
        remove_action.triggered.connect(lambda checked=False, folder=path: self.removeFavoriteRequested.emit(folder))
        menu.addAction(remove_action)
        menu.exec(self.favorites_list.viewport().mapToGlobal(position))

    def _on_favorite_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.set_current_folder(path)
            self.folderSelected.emit(path)

    def _on_favorite_changed(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.favoriteSearchToggled.emit(path, item.checkState() == Qt.Checked)
