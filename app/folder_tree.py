from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from app.utils import scale_px


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

        favorites_header = QHBoxLayout()
        self.favorites_label = QLabel("Favorites")
        self.favorites_label.setStyleSheet("QLabel { color: #5ea7ff; font-weight: 600; }")
        favorites_header.addWidget(self.favorites_label)
        self.add_favorite_button = QPushButton("Add")
        self.remove_favorite_button = QPushButton("Remove")
        self.add_favorite_button.clicked.connect(self._emit_add_favorite)
        self.remove_favorite_button.clicked.connect(self._emit_remove_favorite)
        favorites_header.addWidget(self.add_favorite_button)
        favorites_header.addWidget(self.remove_favorite_button)

        self.model = QFileSystemModel(self)
        self.model.setRootPath(QDir.rootPath())
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(scale_px(16, self))
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.tree.setHorizontalScrollMode(QTreeView.ScrollPerPixel)
        self.tree.setMinimumWidth(0)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree.doubleClicked.connect(self._on_tree_double_clicked)

        favorites_panel = QWidget()
        favorites_layout = QVBoxLayout(favorites_panel)
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        favorites_layout.addLayout(favorites_header)
        favorites_layout.addWidget(self.favorites_list, 1)

        folders_panel = QWidget()
        folders_layout = QVBoxLayout(folders_panel)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.addWidget(QLabel("Folders"))
        folders_layout.addWidget(self.tree, 1)

        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.addWidget(favorites_panel)
        self.vertical_splitter.addWidget(folders_panel)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setSizes([scale_px(180, self), scale_px(420, self)])
        self.vertical_splitter.setOpaqueResize(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
            item = QListWidgetItem(str(path))
            item.setData(Qt.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = True if enabled_favorites is None else path in enabled_favorites
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.favorites_list.addItem(item)
        self.favorites_list.blockSignals(False)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        path = Path(self.model.filePath(current))
        if path.exists():
            self._current_folder = path
            self.folderSelected.emit(path)

    def _on_tree_double_clicked(self, index: QModelIndex) -> None:
        path = Path(self.model.filePath(index))
        if path.exists():
            self.folderOpenRequested.emit(path)

    def _on_favorite_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.set_current_folder(path)
            self.folderSelected.emit(path)

    def _emit_add_favorite(self) -> None:
        if self._current_folder:
            self.addFavoriteRequested.emit(self._current_folder)

    def _emit_remove_favorite(self) -> None:
        item = self.favorites_list.currentItem()
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.removeFavoriteRequested.emit(path)

    def _on_favorite_changed(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.favoriteSearchToggled.emit(path, item.checkState() == Qt.Checked)
