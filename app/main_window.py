from __future__ import annotations

from datetime import datetime
import ctypes
import os
import re
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QImageReader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.associated_browser import AssociatedBrowserDialog
from app.cache_worker import CacheWorker
from app.favorites import FavoritesStore
from app.favorites_index import FavoritesIndexStore, FavoritesIndexWorker
from app.folder_tree import FolderBrowser
from app.models import THUMBNAIL_DIMENSIONS, ThumbnailSize
from app.naming_presets import NamingPresetDialog
from app.scanner import ScanWorker
from app.thumbnail_grid import ThumbnailGrid
from app.thumbnailer import ThumbnailWorker
from app.utils import (
    format_type_label,
    is_drive_root,
    open_fbx_in_viewer,
    open_folder_in_explorer,
    open_video_in_vlc,
    scale_px,
)
from app.viewer import ViewerWindow


APP_USER_MODEL_ID = "TextureBrowser.TextureBrowser"
TEXTURE_ROLE_TERMS = {
    "albedo",
    "alpha",
    "ambient",
    "ao",
    "arm",
    "base",
    "basecolor",
    "basecolour",
    "bump",
    "cavity",
    "col",
    "color",
    "colour",
    "curvature",
    "diff",
    "diffuse",
    "disp",
    "displacement",
    "emission",
    "emissive",
    "emit",
    "gloss",
    "glossiness",
    "height",
    "mask",
    "metal",
    "metallic",
    "metalness",
    "met",
    "mra",
    "mro",
    "mtl",
    "n",
    "nor",
    "norm",
    "normal",
    "nrm",
    "occ",
    "occl",
    "occlusion",
    "opacity",
    "orm",
    "packed",
    "refl",
    "reflect",
    "reflection",
    "reflectivity",
    "rough",
    "roughness",
    "rgh",
    "rma",
    "spec",
    "specular",
    "trans",
    "transparency",
    "directx",
    "dx",
    "gl",
    "opengl",
    "unity",
    "unreal",
}
GUESS_NOISE_TERMS = {
    "1k",
    "2k",
    "4k",
    "8k",
    "16k",
    "preview",
    "surface",
    "texture",
    "material",
    "mat",
    "map",
    "t",
    "tex",
    "tx",
}
ROLE_SORT_ORDER = [
    "basecolor",
    "basecolour",
    "albedo",
    "diffuse",
    "color",
    "colour",
    "ao",
    "n",
    "normal",
    "norm",
    "nrm",
    "bump",
    "roughness",
    "rgh",
    "glossiness",
    "gloss",
    "refl",
    "reflectivity",
    "mro",
    "orm",
    "metallic",
    "metalness",
    "met",
    "height",
    "displacement",
    "cavity",
    "opacity",
    "alpha",
    "emissive",
    "specular",
    "preview",
]


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base_path / relative_path


def app_icon() -> QIcon:
    return QIcon(str(resource_path("assets/app_icon.ico")))


def set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Texture Browser")
        self.resize(scale_px(1440, self), scale_px(900, self))

        self.scan_pool = QThreadPool(self)
        self.scan_pool.setMaxThreadCount(1)
        self.cache_pool = QThreadPool(self)
        self.cache_pool.setMaxThreadCount(1)
        self.index_pool = QThreadPool(self)
        self.index_pool.setMaxThreadCount(1)
        self.thumbnail_pool = QThreadPool(self)
        self.thumbnail_pool.setMaxThreadCount(min(8, max(4, os.cpu_count() or 4)))
        self.settings = FavoritesStore()
        self.favorites_index_store = FavoritesIndexStore()
        self.current_scan: ScanWorker | None = None
        self.current_cache: CacheWorker | None = None
        self.current_favorites_index: FavoritesIndexWorker | None = None
        self.current_root: Path | None = None
        self.items = []
        self._folder_items = []
        self._favorite_items = []
        self._favorite_index_signature: tuple[str, ...] = ()
        self._favorite_index_ready = False
        self._thumb_jobs: set[tuple[int, str, int]] = set()
        self._thumbnail_generation = 0
        self._scan_token = 0
        self._scan_found_count = 0
        self._selection_windows: list[AssociatedBrowserDialog] = []
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(80)
        self._prefetch_timer.timeout.connect(self._request_prefetch_thumbnails)

        self.folder_browser = FolderBrowser()
        self.folder_browser.folderSelected.connect(self.select_folder)
        self.folder_browser.folderOpenRequested.connect(self.open_folder_location)
        self.folder_browser.addFavoriteRequested.connect(self.add_favorite)
        self.folder_browser.removeFavoriteRequested.connect(self.remove_favorite)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search, or paste a folder/file path and press Enter...")
        self.search_box.textChanged.connect(self.apply_filter)
        self.search_box.returnPressed.connect(self.browse_to_search_path)
        self.favorites_search_checkbox = QCheckBox("Favorites")
        self.favorites_search_checkbox.toggled.connect(self._favorites_search_toggled)
        self.browse_path_button = QPushButton("Browse Path")
        self.browse_path_button.clicked.connect(self.browse_to_search_path)
        self.seek_button = QPushButton("Seek")
        self.seek_button.clicked.connect(self.seek_selected_item)

        self.grid = ThumbnailGrid()
        self.grid.itemActivated.connect(self.open_viewer)
        self.grid.thumbnailRequested.connect(self.request_thumbnail)
        self.grid.visibleRangeChanged.connect(self.request_visible_thumbnails)
        self.grid.populationProgress.connect(self._handle_population_progress)
        self.grid.populationFinished.connect(self._handle_population_finished)
        self.grid.itemSelectionChanged.connect(self.update_selected_info)
        self.grid.filesDropped.connect(self.import_dropped_files)
        self.grid.associatedRequested.connect(self.open_associated_viewer)
        self.grid.guessRequested.connect(self.open_guess_viewer)

        size_bar = QHBoxLayout()
        self.thumbnails_label = self._section_label("Thumbnails")
        size_bar.addWidget(self.thumbnails_label)
        self.size_buttons = {}
        for size in ThumbnailSize:
            button = QPushButton(size.value)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, chosen=size: self.set_thumbnail_size(chosen))
            self.size_buttons[size] = button
            size_bar.addWidget(button)
        self.extension_filter_box = QLineEdit()
        self.extension_filter_box.setPlaceholderText(".fbx")
        self.extension_filter_box.setMaximumWidth(scale_px(120, self))
        self.extension_filter_box.textChanged.connect(lambda _text: self.apply_filter(self.search_box.text()))
        size_bar.addSpacing(18)
        self.extension_label = self._section_label("Extension")
        size_bar.addWidget(self.extension_label)
        size_bar.addWidget(self.extension_filter_box)
        self.naming_convention_box = QLineEdit()
        self.naming_convention_box.setPlaceholderText("metallic, albedo, roughness, normal")
        self.naming_convention_box.setMinimumWidth(scale_px(280, self))
        self.naming_convention_box.textChanged.connect(self.save_naming_convention)
        size_bar.addSpacing(18)
        self.naming_convention_label = self._section_label("Naming convention")
        size_bar.addWidget(self.naming_convention_label)
        size_bar.addWidget(self.naming_convention_box, 1)
        self.naming_presets_button = QPushButton("Presets")
        self.naming_presets_button.clicked.connect(self.open_naming_presets)
        size_bar.addWidget(self.naming_presets_button)
        size_bar.addStretch(1)

        self.info_label = QLabel("Select an item to see file info.")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "QLabel { color: #d7dde5; background: #2f343a; border: 1px solid #4a5058; padding: 6px 8px; }"
        )

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        search_row = QHBoxLayout()
        search_row.addWidget(self.favorites_search_checkbox)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.browse_path_button)
        search_row.addWidget(self.seek_button)
        right_layout.addLayout(search_row)
        right_layout.addLayout(size_bar)
        right_layout.addWidget(self.info_label)
        right_layout.addWidget(self.grid, 1)

        splitter = QSplitter()
        splitter.addWidget(self.folder_browser)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([scale_px(340, self), scale_px(1100, self)])

        container = QWidget()
        layout = QVBoxLayout(container)
        margin = scale_px(8, self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        choose_root = QPushButton("Choose Root Folder")
        choose_root.clicked.connect(self.choose_root_folder)
        cancel_button = QPushButton("Cancel Scan")
        cancel_button.clicked.connect(self.cancel_scan)
        cache_here_button = QPushButton("Cache Here")
        cache_here_button.clicked.connect(self.cache_current_root)
        toolbar.addWidget(choose_root)
        toolbar.addWidget(cancel_button)
        toolbar.addWidget(cache_here_button)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.favorites = self.settings.load()
        self.folder_browser.set_favorites(self.favorites)

        stored_size = self.settings.load_thumbnail_size()
        size_choice = ThumbnailSize(stored_size) if stored_size in {size.value for size in ThumbnailSize} else ThumbnailSize.MEDIUM
        self.set_thumbnail_size(size_choice)
        self.naming_convention_box.setText(self.settings.load_naming_convention())

        last_root = self.settings.load_last_root()
        if last_root:
            self.current_root = last_root
            self.folder_browser.set_current_folder(last_root)
            self.status_bar.showMessage(f"Ready. Last folder: {last_root}")

    def choose_root_folder(self) -> None:
        start_dir = str(self.current_root or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Root Directory", start_dir)
        if folder:
            path = Path(folder)
            self.folder_browser.set_current_folder(path)
            self.select_folder(path)

    def browse_to_search_path(self) -> None:
        path = self._path_from_search_text()
        if path is None:
            self.status_bar.showMessage("Enter an existing folder or file path to browse to it.")
            return

        if path.is_dir():
            self._set_search_text_without_filter("")
            self.folder_browser.set_current_folder(path)
            self.select_folder(path)
            return

        if path.is_file():
            parent = path.parent
            self._set_search_text_without_filter(path.name)
            self.folder_browser.set_current_folder(parent)
            self.select_folder(parent)

    def _path_from_search_text(self) -> Path | None:
        text = self.search_box.text().strip().strip('"').strip("'")
        if not text:
            return None

        path = Path(os.path.expandvars(text)).expanduser()
        if path.exists():
            return path
        return None

    def _set_search_text_without_filter(self, text: str) -> None:
        self.search_box.blockSignals(True)
        self.search_box.setText(text)
        self.search_box.blockSignals(False)

    def _set_extension_filter_without_filter(self, text: str) -> None:
        self.extension_filter_box.blockSignals(True)
        self.extension_filter_box.setText(text)
        self.extension_filter_box.blockSignals(False)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("QLabel { color: #5ea7ff; font-weight: 600; }")
        return label

    def select_folder(self, path: Path) -> None:
        if not path.exists():
            return

        if is_drive_root(path):
            self.current_root = path
            self.cancel_scan()
            self._scan_token += 1
            self._prefetch_timer.stop()
            self._reset_thumbnail_queue()
            self._folder_items = []
            if not self._using_favorites_search():
                self._show_items([])
            self.status_bar.showMessage(f"Select a folder inside {path} to scan. Drive roots are skipped.")
            return

        self.current_root = path
        self.settings.save_last_root(path)
        self.cancel_scan()
        self._prefetch_timer.stop()
        self._reset_thumbnail_queue()
        self._folder_items = []

        if not self._using_favorites_search():
            self._show_items([])
        self.status_bar.showMessage(f"Scanning {path}...")
        self._scan_token += 1
        self._scan_found_count = 0
        token = self._scan_token
        worker = ScanWorker(path)
        worker.signals.progress.connect(self.status_bar.showMessage)
        worker.signals.batch.connect(
            lambda items, found_count, scan_token=token: self._handle_scan_batch(scan_token, items, found_count)
        )
        worker.signals.result.connect(
            lambda found_count, scan_token=token: self._handle_scan_result(scan_token, found_count)
        )
        worker.signals.error.connect(lambda message, scan_token=token: self._handle_scan_error(scan_token, message))
        worker.signals.finished.connect(lambda scan_token=token: self._scan_finished(scan_token))
        self.current_scan = worker
        self.scan_pool.start(worker)

    def cancel_scan(self) -> None:
        if self.current_scan is not None:
            self.current_scan.cancel()
            self.current_scan = None
        if self.current_cache is not None:
            self.current_cache.cancel()
            self.current_cache = None

    def cache_current_root(self) -> None:
        if self.current_root is None or not self.current_root.exists():
            self.status_bar.showMessage("Select a folder to cache first.")
            return
        if is_drive_root(self.current_root):
            self.status_bar.showMessage("Select a top folder inside the drive before caching.")
            return
        if self.current_cache is not None:
            self.status_bar.showMessage("Thumbnail caching is already running.")
            return

        worker = CacheWorker(self.current_root)
        worker.signals.progress.connect(self.status_bar.showMessage)
        worker.signals.finished.connect(self._cache_finished)
        worker.signals.error.connect(self._cache_failed)
        self.current_cache = worker
        self.status_bar.showMessage(f"Caching thumbnails in {self.current_root}...")
        self.cache_pool.start(worker)

    def _handle_scan_batch(self, scan_token: int, items: list, found_count: int) -> None:
        if scan_token != self._scan_token:
            return
        self._folder_items.extend(items)
        self._scan_found_count = found_count
        if not self._using_favorites_search():
            self.items = self._folder_items
            self.grid.append_items(items)
            self._apply_grid_filter(self.search_box.text(), show_status=False)
        self.status_bar.showMessage(f"Scanning... {found_count} items found")

    def _handle_scan_result(self, scan_token: int, found_count: int) -> None:
        if scan_token != self._scan_token:
            return
        self._scan_found_count = found_count
        if self.current_root in self.favorites:
            self.favorites_index_store.save_index(self.current_root, self._folder_items)
            self._favorite_index_ready = False
        self.update_selected_info()
        self.status_bar.showMessage(f"Found {self.grid.visible_count()} items")

    def _handle_scan_error(self, scan_token: int, message: str) -> None:
        if scan_token != self._scan_token:
            return
        QMessageBox.warning(self, "Scan Error", message)
        self.status_bar.showMessage("Scan failed")

    def _scan_finished(self, scan_token: int) -> None:
        if scan_token == self._scan_token:
            self.current_scan = None

    def _cache_finished(self, cached_count: int) -> None:
        self.current_cache = None
        self.status_bar.showMessage(f"Cached thumbnails for {cached_count} item(s).")
        self.request_visible_thumbnails()

    def _cache_failed(self, message: str) -> None:
        self.current_cache = None
        QMessageBox.warning(self, "Cache Error", message)
        self.status_bar.showMessage("Caching thumbnails failed")

    def request_thumbnail(self, item) -> None:
        size = self._thumbnail_dimension(self.current_thumbnail_size)
        path_key = str(item.preview_path)
        generation = self._thumbnail_generation
        key = (generation, path_key, size)
        if key in self._thumb_jobs:
            return
        self._thumb_jobs.add(key)
        worker = ThumbnailWorker(item, size, generation)
        worker.signals.ready.connect(self._thumbnail_ready)
        self.thumbnail_pool.start(worker)

    def request_visible_thumbnails(self) -> None:
        self._queue_thumbnail_items(self.grid.visible_items(), prioritize_videos=False)
        self._prefetch_timer.start()

    def _thumbnail_ready(self, generation: int, path_key: str, size: int, pixmap) -> None:
        self._thumb_jobs.discard((generation, path_key, size))
        if generation != self._thumbnail_generation:
            return
        if size != self._thumbnail_dimension(self.current_thumbnail_size):
            return
        self.grid.set_thumbnail(path_key, pixmap)
        if self.thumbnail_pool.activeThreadCount() < 2:
            self.request_visible_thumbnails()

    def set_thumbnail_size(self, size: ThumbnailSize) -> None:
        self.current_thumbnail_size = size
        self.settings.save_thumbnail_size(size.value)
        for thumb_size, button in self.size_buttons.items():
            button.setChecked(thumb_size == size)
        self._reset_thumbnail_queue()
        self.grid.set_thumbnail_size(self._thumbnail_dimension(size))
        self.request_visible_thumbnails()

    def _thumbnail_dimension(self, size: ThumbnailSize) -> int:
        return scale_px(THUMBNAIL_DIMENSIONS[size], self)

    def save_naming_convention(self, text: str) -> None:
        self.settings.save_naming_convention(text)

    def open_naming_presets(self) -> None:
        dialog = NamingPresetDialog(
            self.settings.load_naming_presets(),
            self.naming_convention_box.text(),
            self,
        )
        dialog.presetsChanged.connect(self.settings.save_naming_presets)
        dialog.presetApplied.connect(self.apply_naming_preset)
        dialog.exec()

    def apply_naming_preset(self, convention: str) -> None:
        self.naming_convention_box.setText(convention)
        self.settings.save_naming_convention(convention)
        self.status_bar.showMessage("Naming convention preset loaded.")

    def apply_filter(self, text: str) -> None:
        if self._using_favorites_search():
            if not self._ensure_favorites_items():
                return
        elif self.items is not self._folder_items:
            self._restore_folder_items()
        self._apply_grid_filter(text)

    def _apply_grid_filter(self, text: str, show_status: bool = True) -> None:
        self.grid.apply_filter(text, self.extension_filter_box.text())
        self.request_visible_thumbnails()
        self.update_selected_info()
        if show_status:
            self.status_bar.showMessage(f"Found {self.grid.visible_count()} items")

    def _favorites_search_toggled(self, checked: bool) -> None:
        if checked:
            if not self._ensure_favorites_items():
                return
            self._apply_grid_filter(self.search_box.text())
            return
        self._restore_folder_items()
        self._apply_grid_filter(self.search_box.text())

    def _using_favorites_search(self) -> bool:
        return self.favorites_search_checkbox.isChecked()

    def _favorite_signature(self) -> tuple[str, ...]:
        return tuple(sorted(str(path.resolve()) for path in self.favorites if path.exists()))

    def _ensure_favorites_items(self) -> bool:
        if not self.favorites:
            self._favorite_items = []
            self._favorite_index_ready = True
            self._favorite_index_signature = ()
            self._show_items([])
            self.status_bar.showMessage("Add folders to Favorites first.")
            return True

        signature = self._favorite_signature()
        if self._favorite_index_ready and signature == self._favorite_index_signature:
            if self.items is not self._favorite_items:
                self._show_items(self._favorite_items)
            return True

        if self.current_favorites_index is not None:
            self.status_bar.showMessage("Loading favorites index...")
            return False

        worker = FavoritesIndexWorker([path for path in self.favorites if path.exists()], self.favorites_index_store)
        worker.signals.progress.connect(self.status_bar.showMessage)
        worker.signals.finished.connect(
            lambda items, root_count, worker_signature=signature: self._favorites_index_finished(
                worker_signature,
                items,
                root_count,
            )
        )
        worker.signals.error.connect(self._favorites_index_failed)
        self.current_favorites_index = worker
        self.status_bar.showMessage("Loading favorites index...")
        self.index_pool.start(worker)
        return False

    def _favorites_index_finished(
        self,
        signature: tuple[str, ...],
        items: list,
        root_count: int,
    ) -> None:
        self.current_favorites_index = None
        self._favorite_items = items
        self._favorite_index_signature = signature
        self._favorite_index_ready = True
        if self._using_favorites_search() and signature == self._favorite_signature():
            self._show_items(self._favorite_items)
            self._apply_grid_filter(self.search_box.text(), show_status=False)
            self.status_bar.showMessage(
                f"Loaded favorites index for {root_count} folder(s). {self.grid.visible_count()} items found"
            )

    def _favorites_index_failed(self, message: str) -> None:
        self.current_favorites_index = None
        self._favorite_index_ready = False
        QMessageBox.warning(self, "Favorites Index Error", message)
        self.status_bar.showMessage("Favorites index failed")

    def _restore_folder_items(self) -> None:
        self._show_items(self._folder_items)

    def _show_items(self, items: list) -> None:
        self._prefetch_timer.stop()
        self._reset_thumbnail_queue()
        self.items = items
        self.grid.set_items(items)
        self.update_selected_info()

    def seek_selected_item(self) -> None:
        current = self.grid.currentItem()
        if current is None:
            self.status_bar.showMessage("Select an item to seek.")
            return

        self._set_search_text_without_filter("")
        self._set_extension_filter_without_filter("")
        self.apply_filter("")

        if current.isHidden():
            self.status_bar.showMessage("Selected item is hidden by the default image view.")
            return

        self.grid.setCurrentItem(current)
        self.grid.scrollToItem(current, QAbstractItemView.PositionAtCenter)
        self.grid.setFocus(Qt.OtherFocusReason)
        item = current.data(Qt.UserRole)
        self.status_bar.showMessage(f"Seeked to {item.display_name}.")

    def update_selected_info(self) -> None:
        current = self.grid.currentItem()
        if current is None or current.isHidden():
            self.info_label.setText("Select an item to see file info.")
            return

        item = current.data(Qt.UserRole)
        if item is None:
            self.info_label.setText("Select an item to see file info.")
            return

        info_parts = [format_type_label(item)]
        path = item.preview_path

        dimensions = self._image_dimensions_label(path)
        if dimensions:
            info_parts.append(dimensions)

        if item.sequence:
            frame_count = len(item.sequence.frame_paths)
            info_parts.append(f"{frame_count} frames")

        file_size = self._file_size_label(path)
        if file_size:
            info_parts.append(file_size)

        modified = self._modified_label(path)
        if modified:
            info_parts.append(modified)

        self.info_label.setText(f"{item.display_name}    " + "    |    ".join(info_parts))

    def _image_dimensions_label(self, path: Path) -> str:
        reader = QImageReader(str(path))
        size = reader.size()
        if not size.isValid():
            return ""
        return f"{size.width()} x {size.height()} px"

    def _file_size_label(self, path: Path) -> str:
        try:
            size = path.stat().st_size
        except OSError:
            return ""

        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return ""

    def _modified_label(self, path: Path) -> str:
        try:
            timestamp = path.stat().st_mtime
        except OSError:
            return ""
        modified = datetime.fromtimestamp(timestamp)
        return f"Modified {modified:%Y-%m-%d %H:%M}"

    def add_favorite(self, path: Path) -> None:
        if path not in self.favorites:
            self.favorites.append(path)
            self.settings.save(self.favorites)
            self.folder_browser.set_favorites(self.favorites)
            self._favorite_index_ready = False
            self._favorite_index_signature = ()

    def remove_favorite(self, path: Path) -> None:
        self.favorites = [favorite for favorite in self.favorites if favorite != path]
        self.settings.save(self.favorites)
        self.folder_browser.set_favorites(self.favorites)
        self._favorite_items = [
            item
            for item in self._favorite_items
            if not (item.folder == path or path in item.folder.parents)
        ]
        self._favorite_index_ready = False
        self._favorite_index_signature = ()
        if self._using_favorites_search():
            self.apply_filter(self.search_box.text())

    def import_dropped_files(self, paths: list[Path]) -> None:
        if self.current_root is None or not self.current_root.is_dir() or is_drive_root(self.current_root):
            self.status_bar.showMessage("Select a destination folder before dropping files.")
            return

        copied = 0
        skipped = 0
        for source in paths:
            if not source.is_file():
                skipped += 1
                continue

            destination = self._unique_drop_destination(self.current_root / source.name)
            try:
                if source.resolve() == destination.resolve():
                    skipped += 1
                    continue
                shutil.copy2(source, destination)
                copied += 1
            except OSError:
                skipped += 1

        if copied:
            self.status_bar.showMessage(f"Imported {copied} file(s) into {self.current_root}.")
            self.select_folder(self.current_root)
        elif skipped:
            self.status_bar.showMessage("No files were imported.")

    def _unique_drop_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination

        stem = destination.stem
        suffix = destination.suffix
        folder = destination.parent
        index = 1
        while True:
            label = "copy" if index == 1 else f"copy {index}"
            candidate = folder / f"{stem} {label}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def open_folder_location(self, path: Path) -> None:
        open_folder_in_explorer(path)
        self.status_bar.showMessage(f"Opened folder: {path}")

    def open_viewer(self, item) -> None:
        if item.is_video:
            if open_video_in_vlc(item.preview_path):
                self.status_bar.showMessage(f"Opening in VLC: {item.preview_path.name}")
            else:
                QMessageBox.warning(
                    self,
                    "VLC Not Found",
                    "VLC could not be found. Install VLC or add vlc.exe to PATH, then try again.",
                )
            return

        if item.is_model:
            viewer_name = open_fbx_in_viewer(item.preview_path)
            if viewer_name:
                self.status_bar.showMessage(f"Opening FBX in {viewer_name}: {item.preview_path.name}")
            else:
                QMessageBox.warning(
                    self,
                    "FBX Viewer Not Found",
                    "No FBX viewer could be found. Install Blender or set a default app for .fbx files.",
                )
            return

        items = [
            media_item
            for media_item in self.grid.filtered_items()
            if not media_item.is_video and not media_item.is_model
        ]
        current_index = -1
        for index, media_item in enumerate(items):
            if media_item.preview_path == item.preview_path and media_item.display_name == item.display_name:
                current_index = index
                break
        if current_index < 0:
            current_index = 0
        viewer = ViewerWindow(items, current_index, self)
        viewer.exec()

    def open_associated_viewer(self, item) -> None:
        associated_items = self._associated_items_for(item)
        if not associated_items:
            self.status_bar.showMessage("No associated textures found.")
            return

        current_index = 0
        for index, associated_item in enumerate(associated_items):
            if associated_item.preview_path == item.preview_path and associated_item.display_name == item.display_name:
                current_index = index
                break

        self.status_bar.showMessage(f"Showing {len(associated_items)} associated texture(s).")
        self._show_selection_browser(
            associated_items,
            current_index,
            "Associated Textures",
            "associated texture(s)",
        )

    def open_guess_viewer(self, item) -> None:
        guessed_items = self._guessed_items_for(item)
        if not guessed_items:
            self.status_bar.showMessage("No guessed associates found.")
            return

        current_index = 0
        for index, guessed_item in enumerate(guessed_items):
            if guessed_item.preview_path == item.preview_path and guessed_item.display_name == item.display_name:
                current_index = index
                break

        self.status_bar.showMessage(f"Showing {len(guessed_items)} guessed associate(s).")
        self._show_selection_browser(
            guessed_items,
            current_index,
            "Guessed Associates",
            "guessed texture(s)",
        )

    def _show_selection_browser(
        self,
        items: list,
        current_index: int,
        window_title: str,
        count_label: str,
    ) -> None:
        while len(self._selection_windows) >= 6:
            oldest = self._selection_windows.pop(0)
            oldest.close()

        browser = AssociatedBrowserDialog(
            items,
            current_index,
            self._thumbnail_dimension(self.current_thumbnail_size),
            self,
            window_title,
            count_label,
        )
        browser.setModal(False)
        browser.setAttribute(Qt.WA_DeleteOnClose, True)
        browser.finished.connect(lambda _result, dialog=browser: self._forget_selection_window(dialog))
        self._selection_windows.append(browser)
        browser.show()

    def _forget_selection_window(self, dialog: AssociatedBrowserDialog) -> None:
        if dialog in self._selection_windows:
            self._selection_windows.remove(dialog)

    def _associated_items_for(self, item) -> list:
        if item.is_video or item.is_model:
            return []

        convention_terms = self._convention_token_groups(self.naming_convention_box.text())
        if not convention_terms:
            return [item]

        candidates = [
            media_item
            for media_item in self.items
            if media_item.folder == item.folder and not media_item.is_video and not media_item.is_model
        ]
        selected_tokens = self._name_tokens(item.preview_path.stem)
        selected_has_role = self._candidate_has_convention_role(selected_tokens, convention_terms)
        seed_candidate = self._guess_seed_candidate(item, candidates, convention_terms)
        if seed_candidate is None:
            shared_tokens = self._guess_identity_tokens(item.preview_path.stem, convention_terms)
        else:
            shared_tokens = self._shared_guess_tokens(item, seed_candidate, convention_terms)
        if not shared_tokens:
            return [item]

        matches: dict[tuple[Path, str], object] = {}
        for candidate in candidates:
            candidate_tokens = self._name_tokens(candidate.preview_path.stem)
            if not self._candidate_has_convention_role(candidate_tokens, convention_terms):
                continue
            if not self._guess_identity_matches(shared_tokens, candidate, convention_terms):
                continue
            matches[(candidate.preview_path, candidate.display_name)] = candidate

        if (item.preview_path, item.display_name) not in matches:
            matches[(item.preview_path, item.display_name)] = item

        return sorted(
            matches.values(),
            key=lambda media_item: self._association_sort_key(media_item, item, convention_terms),
        )

    def _guessed_items_for(self, item) -> list:
        if item.is_video or item.is_model:
            return []

        convention_terms = self._convention_token_groups(self.naming_convention_box.text())
        candidates = [
            media_item
            for media_item in self.items
            if media_item.folder == item.folder and not media_item.is_video and not media_item.is_model
        ]
        seed_candidate = self._guess_seed_candidate(item, candidates, convention_terms)
        if seed_candidate is None:
            return [item]

        shared_tokens = self._shared_guess_tokens(item, seed_candidate, convention_terms)
        if not shared_tokens:
            return [item]

        matches: dict[tuple[Path, str], object] = {}
        for candidate in candidates:
            if not self._guess_identity_matches(shared_tokens, candidate, convention_terms):
                continue
            matches[(candidate.preview_path, candidate.display_name)] = candidate

        if (item.preview_path, item.display_name) not in matches:
            matches[(item.preview_path, item.display_name)] = item

        return sorted(
            matches.values(),
            key=lambda media_item: self._association_sort_key(media_item, item, convention_terms),
        )

    def _name_tokens(self, stem: str) -> list[str]:
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
        return self._unique_terms(re.findall(r"[a-z0-9]+", spaced.lower()))

    def _association_sort_key(self, media_item, selected_item, convention_terms: list[list[str]]) -> tuple[int, int, str]:
        if media_item.preview_path == selected_item.preview_path and media_item.display_name == selected_item.display_name:
            return (0, 0, media_item.display_name.lower())

        tokens = self._name_tokens(media_item.preview_path.stem)
        selected_tokens = self._name_tokens(selected_item.preview_path.stem)
        role_order = self._role_sort_order(tokens)
        selected_role_order = self._role_sort_order(selected_tokens)
        term_order = len(convention_terms) + 1
        for index, term_tokens in enumerate(convention_terms):
            if self._find_token_span(tokens, term_tokens)[0] >= 0:
                term_order = index + 1
                break
        effective_order = role_order if role_order <= len(ROLE_SORT_ORDER) else term_order
        if role_order == selected_role_order:
            effective_order += len(ROLE_SORT_ORDER)
        return (1, effective_order, media_item.display_name.lower())

    def _guess_seed_candidate(self, item, candidates, convention_terms: list[list[str]]):
        selected_tokens = self._guess_identity_tokens(item.preview_path.stem, convention_terms)
        if not selected_tokens:
            return None

        best_candidate = None
        best_score = 0
        for candidate in candidates:
            if candidate.preview_path == item.preview_path and candidate.display_name == item.display_name:
                continue
            shared_tokens = self._shared_guess_tokens(item, candidate, convention_terms)
            if not shared_tokens:
                continue

            candidate_tokens = self._name_tokens(candidate.preview_path.stem)
            role_bonus = 2 if self._candidate_has_convention_role(candidate_tokens, convention_terms) else 0
            score = sum(self._guess_token_weight(token) for token in shared_tokens) + role_bonus
            if score > best_score:
                best_score = score
                best_candidate = candidate
        return best_candidate

    def _guess_identity_tokens(self, stem: str, convention_terms: list[list[str]] | None = None) -> list[str]:
        role_terms = set(TEXTURE_ROLE_TERMS)
        if convention_terms is not None:
            role_terms.update("".join(term_tokens) for term_tokens in convention_terms)
            for term_tokens in convention_terms:
                role_terms.update(term_tokens)

        tokens = []
        for token in self._name_tokens(stem):
            normalized = re.sub(r"\d+$", "", token) or token
            if normalized in role_terms or normalized in GUESS_NOISE_TERMS:
                continue
            tokens.append(normalized)
        return self._unique_terms(tokens)

    def _shared_guess_tokens(self, left_item, right_item, convention_terms: list[list[str]] | None = None) -> list[str]:
        left_tokens = self._guess_identity_tokens(left_item.preview_path.stem, convention_terms)
        right_tokens = self._guess_identity_tokens(right_item.preview_path.stem, convention_terms)
        shared: list[str] = []
        for left_token in left_tokens:
            if any(self._guess_tokens_match(left_token, right_token) for right_token in right_tokens):
                shared.append(left_token)
        return shared

    def _guess_identity_matches(
        self,
        shared_tokens: list[str],
        candidate,
        convention_terms: list[list[str]] | None = None,
    ) -> bool:
        candidate_tokens = self._guess_identity_tokens(candidate.preview_path.stem, convention_terms)
        for shared_token in shared_tokens:
            if not any(self._guess_tokens_match(shared_token, candidate_token) for candidate_token in candidate_tokens):
                return False
        return True

    def _guess_token_weight(self, token: str) -> int:
        if token in {"frame", "sheet", "sheets", "panel", "wall", "floor"}:
            return 4
        if token.isdigit():
            return 6
        return max(6, min(18, len(token) * 2))

    def _guess_tokens_match(self, left_token: str, right_token: str) -> bool:
        if left_token == right_token:
            return True
        shorter, longer = sorted((left_token, right_token), key=len)
        return len(shorter) >= 6 and longer.startswith(shorter)

    def _candidate_has_convention_role(self, tokens: list[str], convention_terms: list[list[str]]) -> bool:
        for term_tokens in convention_terms:
            if self._find_token_span(tokens, term_tokens)[0] >= 0:
                return True
            joined_term = "".join(term_tokens)
            if any(self._role_token_matches(joined_term, token) for token in tokens):
                return True
        return False

    def _role_sort_order(self, tokens: list[str]) -> int:
        for index, role in enumerate(ROLE_SORT_ORDER, start=1):
            if any(self._role_token_matches(role, token) for token in tokens):
                return index
        return len(ROLE_SORT_ORDER) + 1

    def _comma_terms(self, text: str) -> list[str]:
        return self._unique_terms(
            re.sub(r"[^a-z0-9]+", "", term.lower())
            for term in text.split(",")
            if term.strip()
        )

    def _convention_token_groups(self, text: str) -> list[list[str]]:
        groups: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for term in text.split(","):
            tokens = tuple(self._name_tokens(term))
            if not tokens or tokens in seen:
                continue
            seen.add(tokens)
            groups.append(list(tokens))
        return groups

    def _search_words(self, text: str) -> list[str]:
        return self._unique_terms(re.findall(r"[a-z0-9]+", text.lower()))

    def _unique_terms(self, terms) -> list[str]:
        unique = []
        seen = set()
        for term in terms:
            if not term or term in seen:
                continue
            seen.add(term)
            unique.append(term)
        return unique

    def _variant_key(self, stem: str, variant_terms: list[list[str]]) -> str | None:
        tokens = self._name_tokens(stem)
        if not tokens:
            return None

        best_key: list[str] | None = None
        best_match_size = 0
        for term_tokens in variant_terms:
            start_index, match_length = self._find_token_span(tokens, term_tokens)
            if start_index < 0:
                continue

            key_tokens = tokens[:start_index] + ["{texture}"] + tokens[start_index + match_length :]
            if len(term_tokens) > best_match_size:
                best_match_size = len(term_tokens)
                best_key = key_tokens

        if best_key is None:
            return None
        return "_".join(best_key)

    def _variant_search_text(self, stem: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", stem.lower())

    def _find_subsequence(self, tokens: list[str], pattern: list[str]) -> int:
        if not tokens or not pattern or len(pattern) > len(tokens):
            return -1
        last_start = len(tokens) - len(pattern)
        for start_index in range(last_start + 1):
            if tokens[start_index : start_index + len(pattern)] == pattern:
                return start_index
        return -1

    def _find_token_span(self, tokens: list[str], pattern: list[str]) -> tuple[int, int]:
        if not tokens or not pattern:
            return (-1, 0)

        joined_pattern = "".join(self._normalize_role_token(token) for token in pattern)
        max_span = min(len(pattern), len(tokens))
        for start_index in range(len(tokens)):
            for span_length in range(max_span, 0, -1):
                end_index = start_index + span_length
                if end_index > len(tokens):
                    continue
                joined_tokens = "".join(
                    self._normalize_role_token(token) for token in tokens[start_index:end_index]
                )
                if joined_tokens == joined_pattern:
                    return (start_index, span_length)
        return (-1, 0)

    def _normalize_role_token(self, token: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "", token.lower())
        stripped = re.sub(r"\d+$", "", normalized)
        return stripped or normalized

    def _role_token_matches(self, role: str, token: str) -> bool:
        return self._normalize_role_token(role) == self._normalize_role_token(token)

    def _handle_population_progress(self, added_count: int, total_count: int) -> None:
        if self.current_scan is None:
            self.status_bar.showMessage(f"Preparing items... {added_count}/{total_count}")
        if added_count <= self.grid.total_count():
            self.request_visible_thumbnails()

    def _handle_population_finished(self, visible_count: int) -> None:
        self.request_visible_thumbnails()
        if self.current_scan is None:
            self.status_bar.showMessage(f"Found {visible_count} items")

    def _request_prefetch_thumbnails(self) -> None:
        if self.thumbnail_pool.activeThreadCount() >= 3:
            self._prefetch_timer.start()
            return
        self._queue_thumbnail_items(self.grid.prefetch_items(), prioritize_videos=True, limit=40)

    def _reset_thumbnail_queue(self) -> None:
        self._thumbnail_generation += 1
        self._thumb_jobs.clear()
        self.thumbnail_pool.clear()

    def _queue_thumbnail_items(self, items, prioritize_videos: bool, limit: int | None = None) -> None:
        if not items:
            return

        images = [item for item in items if not item.is_video]
        videos = [item for item in items if item.is_video]
        ordered = videos + images if prioritize_videos else images + videos

        if limit is not None:
            ordered = ordered[:limit]

        for item in ordered:
            self.grid.thumbnailRequested.emit(item)


def run() -> None:
    set_windows_app_user_model_id()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Texture Browser")
    app.setOrganizationName("TextureBrowser")
    icon = app_icon()
    app.setWindowIcon(icon)
    app.setStyle("Fusion")

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())
