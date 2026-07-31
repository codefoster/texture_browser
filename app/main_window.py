from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
import ctypes
import os
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QListWidget,
    QSplashScreen,
    QSplitter,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.associated_browser import AssociatedBrowserDialog
from app.cache_worker import CacheWorker
from app.channel_inspector import ChannelInspectorDialog
from app.favorites import FavoritesStore
from app.favorites_index import FavoritesIndexStore, FavoritesIndexWorker
from app.folder_tree import FolderBrowser
from app.godot_renderer import launch_material_renderer
from app.media_dimensions import media_dimensions
from app.models import THUMBNAIL_DIMENSIONS, ThumbnailSize
from app.naming_presets import NamingPresetDialog
from app.scanner import ScanWorker
from app.size_filter_worker import SizeFilterWorker
from app.tag_csv_exporter import TagCsvExportWorker
from app.tag_store import TagStore, normalize_tag_name, tag_database_exists
from app.thumbnail_grid import ThumbnailGrid
from app.thumbnailer import ThumbnailWorker
from app.texture_sets import texture_set_for_item, validate_texture_set
from app.platform_services import (
    fbx_handler_hint,
    open_folder,
    open_model_in_viewer,
    open_video_in_vlc,
    open_with_default_app,
    vlc_install_hint,
)
from app.theme import apply_theme
from app.utils import (
    format_type_label,
    find_library_cache_root,
    is_drive_root,
    normalize_path_key,
    scale_px,
)
from app.validation_report import TextureSetValidationDialog
from app.viewer import ViewerWindow
from app.workflow_filter import workflow_filter_predicate


APP_USER_MODEL_ID = "TextureBrowser.TextureBrowser"
ANY_TAG_LABEL = "Any tag"
FOLDER_SCAN_CACHE_MAX_FOLDERS = 8
FOLDER_SCAN_CACHE_MAX_ITEMS = 100_000
FOLDER_SCAN_CACHE_TTL_SECONDS = 600.0
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

IMAGE_SIZE_FILTERS = [
    ("Any size", None),
    ("Up to 48 px", ("max", 48)),
    ("48+ px", ("min", 48)),
    ("Up to 64 px", ("max", 64)),
    ("64+ px", ("min", 64)),
    ("Up to 128 px", ("max", 128)),
    ("128+ px", ("min", 128)),
    ("Up to 256 px", ("max", 256)),
    ("256+ px", ("min", 256)),
    ("Up to 512 px", ("max", 512)),
    ("512+ px", ("min", 512)),
    ("Up to 1K", ("max", 1024)),
    ("1K+", ("min", 1024)),
    ("Up to 2K", ("max", 2048)),
    ("2K+", ("min", 2048)),
    ("Up to 4K", ("max", 4096)),
    ("4K+", ("min", 4096)),
    ("Up to 8K", ("max", 8192)),
    ("8K+", ("min", 8192)),
    ("Up to 16K", ("max", 16384)),
    ("16K+", ("min", 16384)),
]


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base_path / relative_path


def application_version() -> str:
    try:
        return resource_path("VERSION").read_text(encoding="ascii").strip()
    except OSError:
        return ""


def app_icon() -> QIcon:
    icon_name = "app_icon.ico" if sys.platform == "win32" else "app_icon.png"
    return QIcon(str(resource_path(f"assets/{icon_name}")))


def app_splash_pixmap() -> QPixmap:
    pixmap = QPixmap(
        str(
            resource_path(
                "assets/stollnation_cool_logo_for_a_program_called_Texture_Browser_ju_6450916f-8510-416e-ab27-ceb00f104fbc_0.png"
            )
        )
    )
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(720, 405, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def create_splash(message: str = "", screen=None) -> QSplashScreen | None:
    pixmap = app_splash_pixmap()
    if pixmap.isNull():
        return None
    splash = QSplashScreen(pixmap)
    target_screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if target_screen is not None:
        screen_rect = target_screen.availableGeometry()
        splash_rect = splash.frameGeometry()
        splash_rect.moveCenter(screen_rect.center())
        splash.move(splash_rect.topLeft())
    if message:
        splash.showMessage(message, Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
    return splash


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
        version = QApplication.applicationVersion()
        self.setWindowTitle(f"Texture Browser {version}" if version else "Texture Browser")
        self.resize(scale_px(1440, self), scale_px(900, self))

        self.scan_pool = QThreadPool(self)
        self.scan_pool.setMaxThreadCount(1)
        self.cache_pool = QThreadPool(self)
        self.cache_pool.setMaxThreadCount(1)
        self.index_pool = QThreadPool(self)
        self.index_pool.setMaxThreadCount(1)
        self.size_pool = QThreadPool(self)
        self.size_pool.setMaxThreadCount(1)
        self.export_pool = QThreadPool(self)
        self.export_pool.setMaxThreadCount(1)
        self.thumbnail_pool = QThreadPool(self)
        self.thumbnail_pool.setMaxThreadCount(min(8, max(2, (os.cpu_count() or 4) // 2)))
        self.settings = FavoritesStore()
        self.favorites_index_store = FavoritesIndexStore()
        self.current_scan: ScanWorker | None = None
        self.current_cache: CacheWorker | None = None
        self.current_favorites_index: FavoritesIndexWorker | None = None
        self.current_size_filter: SizeFilterWorker | None = None
        self.current_tag_export: TagCsvExportWorker | None = None
        self.current_root: Path | None = None
        self._queued_folder: Path | None = None
        self.sequence_grouping_enabled = self.settings.load_sequence_grouping_enabled()
        self.items = []
        self._folder_items = []
        self._favorite_items = []
        self._folder_scan_cache: OrderedDict[tuple[str, bool], tuple[list, dict[str, int], float]] = OrderedDict()
        self._folder_scan_cache_item_count = 0
        self._loading_cached_folder = False
        self._duplicate_first_keys: dict[str, tuple[Path, str]] = {}
        self._duplicate_hidden_keys: set[tuple[Path, str]] = set()
        self._tag_filter_lookup: dict[Path, set[str]] = {}
        self._tagged_item_keys: set[tuple[Path, str]] = set()
        self._selected_tag_filter = self.settings.load_active_tag_filter()
        self._favorite_index_signature: tuple[str, ...] = ()
        self._favorite_index_ready = False
        self._thumb_jobs: set[tuple[int, str, int]] = set()
        self._thumbnail_generation = 0
        self._scan_token = 0
        self._scan_found_count = 0
        self._selection_windows: list[AssociatedBrowserDialog] = []
        self._tool_windows: list[QDialog] = []
        self._scan_splash: QSplashScreen | None = None
        self._size_filter_token = 0
        self._size_filter_pending = False
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(80)
        self._prefetch_timer.timeout.connect(self._request_prefetch_thumbnails)
        self._search_filter_timer = QTimer(self)
        self._search_filter_timer.setSingleShot(True)
        self._search_filter_timer.setInterval(160)
        self._search_filter_timer.timeout.connect(lambda: self.apply_filter(self.search_box.text()))

        self.folder_browser = FolderBrowser()
        self.folder_browser.folderSelected.connect(self.select_folder)
        self.folder_browser.folderOpenRequested.connect(self.open_folder_location)
        self.folder_browser.addFavoriteRequested.connect(self.add_favorite)
        self.folder_browser.removeFavoriteRequested.connect(self.remove_favorite)
        self.folder_browser.favoriteSearchToggled.connect(self.set_favorite_search_enabled)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files. Use commas for alternatives, or paste a folder/file path and press Enter...")
        self.search_box.setMinimumWidth(0)
        self.search_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.search_box.textChanged.connect(self._schedule_search_filter)
        self.search_box.returnPressed.connect(self.browse_to_search_path)
        self.favorites_search_checkbox = QCheckBox("Favorites")
        self.favorites_search_checkbox.toggled.connect(self._favorites_search_toggled)
        self.sequence_grouping_checkbox = QCheckBox("Sequences")
        self.sequence_grouping_checkbox.setChecked(self.sequence_grouping_enabled)
        self.sequence_grouping_checkbox.toggled.connect(self.set_sequence_grouping_enabled)
        self.hide_duplicates_checkbox = QCheckBox("Hide duplicates")
        self.hide_duplicates_checkbox.setChecked(self.settings.load_hide_duplicates_enabled())
        self.hide_duplicates_checkbox.toggled.connect(self.set_hide_duplicates_enabled)
        self.browse_path_button = QPushButton("Browse Path")
        self.browse_path_button.clicked.connect(self.browse_to_search_path)
        self.seek_button = QPushButton("Seek")
        self.seek_button.clicked.connect(self.seek_selected_item)
        self.material_preview_button = QPushButton("Material Viewer")
        self.material_preview_button.setProperty("variant", "primary")
        self.material_preview_button.setToolTip("Open the material/object viewer for the selected texture set.")
        self.material_preview_button.clicked.connect(self.open_selected_material_renderer)

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
        self.grid.materialSetRequested.connect(self.open_material_set_viewer)
        self.grid.materialRendererRequested.connect(self.open_material_renderer)
        self.grid.validationRequested.connect(self.open_texture_validation)
        self.grid.channelInspectorRequested.connect(self.open_channel_inspector)
        self.grid.tagFileRequested.connect(self.add_tag_to_file)
        self.grid.tagMaterialSetRequested.connect(self.add_tag_to_material_set)
        self.grid.removeTagRequested.connect(self.remove_tag_from_item)

        size_bar = QHBoxLayout()
        size_bar.setSpacing(scale_px(10, self))
        self.thumbnails_label = self._section_label("Thumbnails")
        size_bar.addWidget(self.thumbnails_label)
        self.size_buttons = {}
        size_button_labels = {
            ThumbnailSize.TINY: "T",
            ThumbnailSize.SMALL: "S",
            ThumbnailSize.MEDIUM: "M",
            ThumbnailSize.LARGE: "L",
        }
        for size in ThumbnailSize:
            button = QPushButton(size_button_labels[size])
            button.setCheckable(True)
            button.setToolTip(size.value)
            button.setFixedWidth(scale_px(28, self))
            button.clicked.connect(lambda checked=False, chosen=size: self.set_thumbnail_size(chosen))
            self.size_buttons[size] = button
            size_bar.addWidget(button)
        self.extension_filter_box = QLineEdit()
        self.extension_filter_box.setPlaceholderText(".fbx")
        self.extension_filter_box.setMaximumWidth(scale_px(120, self))
        self.extension_filter_box.textChanged.connect(self._schedule_search_filter)
        size_bar.addSpacing(18)
        self.extension_label = self._section_label("Extension")
        size_bar.addWidget(self.extension_label)
        size_bar.addWidget(self.extension_filter_box)
        self.image_size_filter_box = QComboBox()
        self.image_size_filter_box.setMinimumWidth(scale_px(132, self))
        self.image_size_filter_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        for label, value in IMAGE_SIZE_FILTERS:
            self.image_size_filter_box.addItem(label, value)
        self.image_size_filter_box.currentIndexChanged.connect(self._image_size_filter_changed)
        size_bar.addSpacing(18)
        self.image_size_label = self._section_label("Image size")
        size_bar.addWidget(self.image_size_label)
        size_bar.addWidget(self.image_size_filter_box)
        self.tag_filter_box = QComboBox()
        self.tag_filter_box.setMinimumWidth(scale_px(132, self))
        self.tag_filter_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.tag_filter_box.currentIndexChanged.connect(lambda _index: self._tag_filter_changed())
        size_bar.addSpacing(18)
        self.tag_manager_button = self._section_button("Tag")
        self.tag_manager_button.clicked.connect(self.open_tag_manager)
        size_bar.addWidget(self.tag_manager_button)
        size_bar.addWidget(self.tag_filter_box)
        self.naming_convention_box = QLineEdit()
        self.naming_convention_box.setPlaceholderText("metallic, albedo, roughness, normal")
        self.naming_convention_box.setMinimumWidth(0)
        self.naming_convention_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.naming_convention_box.textChanged.connect(self.save_naming_convention)
        self.naming_convention_box.textChanged.connect(self._workflow_text_changed)
        size_bar.addSpacing(18)
        self.naming_convention_label = self._section_label("Workflow")
        self.workflow_filter_checkbox = QCheckBox()
        self.workflow_filter_checkbox.setToolTip("Filter filenames by the current workflow terms.")
        self.workflow_filter_checkbox.toggled.connect(lambda _checked: self.apply_filter(self.search_box.text()))
        size_bar.addWidget(self.naming_convention_label)
        size_bar.addWidget(self.workflow_filter_checkbox)
        size_bar.addWidget(self.naming_convention_box, 1)
        self.naming_presets_button = QPushButton("Presets")
        self.naming_presets_button.clicked.connect(self.open_naming_presets)
        size_bar.addWidget(self.naming_presets_button)
        size_bar.addStretch(1)

        self.info_label = QLabel("Select an item to see file info.")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        self.info_label.setProperty("variant", "info")

        right_panel = QWidget()
        right_panel.setMinimumWidth(scale_px(100, self))
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        search_row = QHBoxLayout()
        search_row.setSpacing(scale_px(10, self))
        search_row.addWidget(self.favorites_search_checkbox)
        search_row.addWidget(self.sequence_grouping_checkbox)
        search_row.addWidget(self.hide_duplicates_checkbox)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.browse_path_button)
        search_row.addWidget(self.seek_button)
        search_row.addWidget(self.material_preview_button)
        right_layout.addLayout(search_row)
        right_layout.addLayout(size_bar)
        right_layout.addWidget(self.info_label)
        right_layout.addWidget(self.grid, 1)

        splitter = QSplitter()
        splitter.addWidget(self.folder_browser)
        splitter.addWidget(right_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([scale_px(340, self), scale_px(1100, self)])
        self.folder_browser.setMinimumWidth(scale_px(100, self))

        container = QWidget()
        layout = QVBoxLayout(container)
        margin = scale_px(12, self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        choose_root = QPushButton("Choose Root Folder")
        choose_root.setProperty("variant", "primary")
        choose_root.clicked.connect(self.choose_root_folder)
        cancel_button = QPushButton("Cancel Scan")
        cancel_button.clicked.connect(self.cancel_scan_from_ui)
        cache_here_button = QPushButton("Cache Here")
        cache_here_button.clicked.connect(self.cache_current_root)
        self.export_tag_csv_button = QPushButton("Export CSV")
        self.export_tag_csv_button.clicked.connect(self.export_tag_csv)
        self.theme_button = QPushButton("Light Mode" if self.settings.load_theme_mode() == "dark" else "Dark Mode")
        self.theme_button.clicked.connect(self.toggle_theme)
        self.material_viewer_toolbar_button = QPushButton("Material Viewer")
        self.material_viewer_toolbar_button.setProperty("variant", "primary")
        self.material_viewer_toolbar_button.setToolTip("Open the material/object viewer for the selected texture set.")
        self.material_viewer_toolbar_button.clicked.connect(self.open_selected_material_renderer)
        toolbar.addWidget(choose_root)
        toolbar.addWidget(cancel_button)
        toolbar.addWidget(cache_here_button)
        toolbar.addWidget(self.export_tag_csv_button)
        toolbar.addWidget(self.theme_button)
        toolbar_spacer = QWidget()
        toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(toolbar_spacer)
        toolbar.addWidget(self.material_viewer_toolbar_button)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.favorites = self.settings.load()
        self.favorite_search_enabled = set(self.settings.load_favorites_search_enabled(self.favorites))
        if not self.favorite_search_enabled:
            self.favorite_search_enabled = set(self.favorites)
        self.folder_browser.set_favorites(self.favorites, self.favorite_search_enabled)

        stored_size = self.settings.load_thumbnail_size()
        size_choice = ThumbnailSize(stored_size) if stored_size in {size.value for size in ThumbnailSize} else ThumbnailSize.MEDIUM
        self.set_thumbnail_size(size_choice)
        self._restore_image_size_filter()
        self.naming_convention_box.setText(self.settings.load_naming_convention())

        last_root = self.settings.load_last_root()
        if last_root:
            self.current_root = last_root
            self.folder_browser.set_current_folder(last_root)
            self.refresh_tag_filter_options()
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
        label = QLabel(text.upper())
        label.setProperty("variant", "kicker")
        return label

    def _section_button(self, text: str) -> QPushButton:
        button = QPushButton(text.upper())
        button.setFlat(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("variant", "link")
        return button

    def toggle_theme(self) -> None:
        mode = "light" if self.settings.load_theme_mode() == "dark" else "dark"
        self.settings.save_theme_mode(mode)
        apply_theme(QApplication.instance(), mode)
        self.theme_button.setText("Dark Mode" if mode == "light" else "Light Mode")

    def select_folder(self, path: Path) -> None:
        if not path.exists():
            return

        if is_drive_root(path):
            self.current_root = path
            self._queued_folder = None
            self.cancel_scan()
            self._scan_token += 1
            self._prefetch_timer.stop()
            self._reset_thumbnail_queue()
            self._folder_items = []
            self.refresh_tag_filter_options()
            if not self._using_favorites_search():
                self._show_items([])
            self.status_bar.showMessage(f"Select a folder inside {path} to scan. Drive roots are skipped.")
            return

        self.current_root = path
        self.settings.save_last_root(path)
        if self.current_scan is not None:
            self._queued_folder = path
            self.cancel_scan()
            self.status_bar.showMessage(f"Canceling scan. {path} is queued next...")
            return
        if self._load_cached_folder_scan(path):
            return
        self._queued_folder = None
        self._start_scan(path)

    def _folder_scan_cache_key(self, path: Path) -> tuple[str, bool]:
        return (normalize_path_key(path), self.sequence_grouping_enabled)

    def _load_cached_folder_scan(self, path: Path) -> bool:
        key = self._folder_scan_cache_key(path)
        entry = self._folder_scan_cache.get(key)
        if entry is None:
            return False
        cached_items, directory_mtimes, cached_at = entry
        if (
            time.monotonic() - cached_at > FOLDER_SCAN_CACHE_TTL_SECONDS
            or not self._folder_cache_directories_are_current(directory_mtimes)
        ):
            self._discard_folder_scan_cache_entry(key)
            return False
        self._folder_scan_cache.move_to_end(key)
        self._queued_folder = None
        self._prefetch_timer.stop()
        self._reset_thumbnail_queue()
        self._folder_items = list(cached_items)
        self.refresh_tag_filter_options()
        if not self._using_favorites_search():
            self._loading_cached_folder = True
            self._show_items(self._folder_items, fast=True)
            self._apply_grid_filter(self.search_box.text(), show_status=False)
        self.status_bar.showMessage(f"Loading cached scan for {path}...")
        return True

    @staticmethod
    def _folder_cache_mtime_ns(path: Path) -> int | None:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    @classmethod
    def _folder_cache_directories_are_current(cls, directory_mtimes: dict[str, int]) -> bool:
        return all(
            cls._folder_cache_mtime_ns(Path(directory)) == mtime_ns
            for directory, mtime_ns in directory_mtimes.items()
        )

    @classmethod
    def _folder_cache_directory_mtimes(cls, path: Path, items: list) -> dict[str, int]:
        directories = {path, *(item.folder for item in items)}
        signatures: dict[str, int] = {}
        for directory in directories:
            mtime_ns = cls._folder_cache_mtime_ns(directory)
            if mtime_ns is not None:
                signatures[str(directory.resolve())] = mtime_ns
        return signatures

    def _discard_folder_scan_cache_entry(self, key: tuple[str, bool]) -> None:
        entry = self._folder_scan_cache.pop(key, None)
        if entry is not None:
            self._folder_scan_cache_item_count -= len(entry[0])

    def _store_folder_scan_cache(self, path: Path, items: list) -> None:
        directory_mtimes = self._folder_cache_directory_mtimes(path, items)
        if not directory_mtimes:
            return
        key = self._folder_scan_cache_key(path)
        self._discard_folder_scan_cache_entry(key)
        cached_items = list(items)
        self._folder_scan_cache[key] = (cached_items, directory_mtimes, time.monotonic())
        self._folder_scan_cache_item_count += len(cached_items)
        while self._folder_scan_cache and (
            len(self._folder_scan_cache) > FOLDER_SCAN_CACHE_MAX_FOLDERS
            or self._folder_scan_cache_item_count > FOLDER_SCAN_CACHE_MAX_ITEMS
        ):
            _, removed = self._folder_scan_cache.popitem(last=False)
            self._folder_scan_cache_item_count -= len(removed[0])

    def _start_scan(self, path: Path) -> None:
        self._prefetch_timer.stop()
        self._show_scan_splash()
        self._reset_thumbnail_queue()
        self._folder_items = []
        self._reset_duplicate_filter_state()
        self.refresh_tag_filter_options()

        if not self._using_favorites_search():
            self._show_items([])
            self._prime_grid_filter_settings()
        self.status_bar.showMessage(f"Scanning {path}...")
        self._scan_token += 1
        self._scan_found_count = 0
        token = self._scan_token
        worker = ScanWorker(path, self.sequence_grouping_enabled)
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
        self._hide_scan_splash()
        if self.current_scan is not None:
            self.current_scan.cancel()
        if self.current_cache is not None:
            self.current_cache.cancel()
            self.current_cache = None
        self._cancel_size_filter_worker()

    def cancel_scan_from_ui(self) -> None:
        self._queued_folder = None
        self.cancel_scan()
        self.status_bar.showMessage("Canceling scan...")

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
        self._record_duplicate_items(items)
        self._record_tagged_item_keys(items)
        self._scan_found_count = found_count
        if not self._using_favorites_search():
            self.items = self._folder_items
            self.grid.append_items(items)
        self.status_bar.showMessage(f"Scanning... {found_count} items found")

    def _handle_scan_result(self, scan_token: int, found_count: int) -> None:
        if scan_token != self._scan_token:
            return
        self._hide_scan_splash()
        self._scan_found_count = found_count
        if self.current_root is not None:
            self._store_folder_scan_cache(self.current_root, self._folder_items)
        if self.current_root in self.favorites:
            self.favorites_index_store.save_index(self.current_root, self._folder_items, self.sequence_grouping_enabled)
            self._favorite_index_ready = False
        self.update_selected_info()
        self.status_bar.showMessage(f"Found {self.grid.visible_count()} items")

    def _handle_scan_error(self, scan_token: int, message: str) -> None:
        if scan_token != self._scan_token:
            return
        self._hide_scan_splash()
        QMessageBox.warning(self, "Scan Error", message)
        self.status_bar.showMessage("Scan failed")

    def _scan_finished(self, scan_token: int) -> None:
        finished_scan = self.current_scan
        if finished_scan is not None and scan_token == self._scan_token:
            self.current_scan = None
        elif finished_scan is None:
            pass
        else:
            self.current_scan = None

        if self._queued_folder is not None:
            next_path = self._queued_folder
            self._queued_folder = None
            if next_path.exists():
                self.current_root = next_path
                self.settings.save_last_root(next_path)
                self._start_scan(next_path)
        elif scan_token == self._scan_token:
            self._hide_scan_splash()

    def _cache_finished(self, cached_count: int) -> None:
        self.current_cache = None
        self.status_bar.showMessage(f"Cached thumbnails for {cached_count} item(s).")
        self.request_visible_thumbnails()

    def _cache_failed(self, message: str) -> None:
        self.current_cache = None
        QMessageBox.warning(self, "Cache Error", message)
        self.status_bar.showMessage("Caching thumbnails failed")

    def _show_scan_splash(self) -> None:
        if self._scan_splash is not None:
            return
        self._scan_splash = create_splash("Scanning textures...", self.screen())
        if self._scan_splash is None:
            return
        self._scan_splash.show()
        QApplication.processEvents()

    def _hide_scan_splash(self) -> None:
        if self._scan_splash is None:
            return
        self._scan_splash.close()
        self._scan_splash = None

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

    def set_hide_duplicates_enabled(self, enabled: bool) -> None:
        self.settings.save_hide_duplicates_enabled(enabled)
        if not self._duplicate_first_keys and self.items:
            self._rebuild_duplicate_filter_state(self.items)
        self.apply_filter(self.search_box.text())

    def add_tag_to_file(self, item) -> None:
        tag_name = self._prompt_for_tag("Tag File")
        if not tag_name:
            return
        selected_items = self._selected_items_for_action(item)
        tagged_count = self._add_tag_to_items(tag_name, selected_items, scope="file")
        self.refresh_tag_filter_options()
        self.apply_filter(self.search_box.text())
        self.status_bar.showMessage(f"Tagged {tagged_count} file(s) with {tag_name}.")

    def add_tag_to_material_set(self, item) -> None:
        tag_name = self._prompt_for_tag("Tag Material Set")
        if not tag_name:
            return
        tagged_count = 0
        seen: set[tuple[Path, str]] = set()
        for selected_item in self._selected_items_for_action(item):
            texture_set = texture_set_for_item(selected_item, self.items)
            material_items = []
            for material_item in texture_set.items:
                key = (material_item.preview_path, material_item.display_name)
                if key in seen:
                    continue
                seen.add(key)
                material_items.append(material_item)
            tagged_count += self._add_tag_to_items(
                tag_name,
                material_items,
                scope="material_set",
                set_key=texture_set.title,
            )
        self.refresh_tag_filter_options()
        self.apply_filter(self.search_box.text())
        self.status_bar.showMessage(f"Tagged {tagged_count} material set file(s) with {tag_name}.")

    def export_tag_csv(self) -> None:
        tag_name = self._active_tag_name()
        if tag_name is None:
            self.status_bar.showMessage("Choose a tag first, then export CSV.")
            return
        roots = self._tag_roots_for_current_context(existing_only=True)
        if not roots:
            self.status_bar.showMessage("No tagged library roots are available for this export.")
            return
        if self.current_tag_export is not None:
            self.status_bar.showMessage("A tag CSV export is already running.")
            return

        default_root = self.current_root or roots[0]
        default_name = re.sub(r"[^A-Za-z0-9._-]+", "_", tag_name) or "tag_export"
        default_path = default_root / f"{default_name}_materials.csv"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Tag CSV",
            str(default_path),
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        worker = TagCsvExportWorker(roots, tag_name, Path(file_path))
        worker.signals.progress.connect(self.status_bar.showMessage)
        worker.signals.finished.connect(self._tag_csv_export_finished)
        worker.signals.error.connect(self._tag_csv_export_failed)
        self.current_tag_export = worker
        self.status_bar.showMessage(f"Exporting CSV for tag {tag_name}...")
        self.export_pool.start(worker)

    def remove_tag_from_item(self, item) -> None:
        selected_items = self._selected_items_for_action(item)
        root = self._tag_root_for_item(item, create=False)
        if root is None:
            self.status_bar.showMessage("This file has no library tag database yet.")
            return
        store = TagStore(root)
        tags = store.tags_for_items(selected_items)
        if not tags:
            self.status_bar.showMessage("No tags found on the selected file(s).")
            return
        tag_name, ok = QInputDialog.getItem(self, "Remove Tag", "Tag", tags, 0, False)
        if not ok or not tag_name:
            return
        removed_count = self._remove_tag_from_items(tag_name, selected_items)
        self.refresh_tag_filter_options()
        self.apply_filter(self.search_box.text())
        self.status_bar.showMessage(f"Removed {tag_name} from {removed_count} file(s).")

    def _selected_items_for_action(self, clicked_item) -> list:
        selected_items = self.grid.selected_media_items()
        clicked_key = (clicked_item.preview_path, clicked_item.display_name)
        if any((item.preview_path, item.display_name) == clicked_key for item in selected_items):
            return selected_items
        return [clicked_item]

    def _focused_media_item(self):
        selected_items = self.grid.selected_media_items()
        if selected_items:
            return selected_items[0]
        current = self.grid.currentItem()
        if current is None:
            return None
        return current.data(Qt.UserRole)

    def _add_tag_to_items(self, tag_name: str, items: list, scope: str, set_key: str = "") -> int:
        tagged_count = 0
        for root, root_items in self._items_grouped_by_tag_root(items, create=True).items():
            tagged_count += TagStore(root).add_items(tag_name, root_items, scope=scope, set_key=set_key)
        return tagged_count

    def _remove_tag_from_items(self, tag_name: str, items: list) -> int:
        removed_count = 0
        for root, root_items in self._items_grouped_by_tag_root(items, create=False).items():
            removed_count += TagStore(root).remove_items(tag_name, root_items)
        return removed_count

    def _items_grouped_by_tag_root(self, items: list, create: bool) -> dict[Path, list]:
        grouped: dict[Path, list] = {}
        for item in items:
            root = self._tag_root_for_item(item, create=create)
            if root is None:
                continue
            grouped.setdefault(root, []).append(item)
        return grouped

    def open_tag_manager(self) -> None:
        roots = self._tag_roots_for_manager()
        if not roots:
            self.status_bar.showMessage("Select a folder or favorite library first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Tags")
        dialog.resize(scale_px(360, self), scale_px(420, self))
        layout = QVBoxLayout(dialog)

        tag_list = QListWidget(dialog)
        layout.addWidget(tag_list, 1)

        buttons_row = QHBoxLayout()
        add_button = QPushButton("Add Tag", dialog)
        delete_button = QPushButton("Delete Tag", dialog)
        close_button = QPushButton("Close", dialog)
        buttons_row.addWidget(add_button)
        buttons_row.addWidget(delete_button)
        buttons_row.addStretch(1)
        buttons_row.addWidget(close_button)
        layout.addLayout(buttons_row)

        def refresh_list() -> None:
            current_name = tag_list.currentItem().text() if tag_list.currentItem() is not None else ""
            tag_list.clear()
            for tag_name in self._all_tags_for_roots(roots):
                tag_list.addItem(tag_name)
            if current_name:
                for row in range(tag_list.count()):
                    item = tag_list.item(row)
                    if item is not None and item.text().lower() == current_name.lower():
                        tag_list.setCurrentRow(row)
                        break

        def add_tag() -> None:
            tag_name = self._prompt_for_tag("Add Tag")
            if not tag_name:
                return
            created = False
            for root in roots:
                created = TagStore(root).create_tag(tag_name) or created
            if not created:
                return
            self.refresh_tag_filter_options()
            refresh_list()
            self.status_bar.showMessage(f"Added tag {tag_name}.")

        def delete_tag() -> None:
            current_item = tag_list.currentItem()
            if current_item is None:
                self.status_bar.showMessage("Select a tag to delete.")
                return
            tag_name = normalize_tag_name(current_item.text())
            if not tag_name:
                return
            removed = 0
            for root in roots:
                if tag_database_exists(root):
                    removed += TagStore(root).delete_tag(tag_name)
            if self._active_tag_name() and self._active_tag_name().lower() == tag_name.lower():
                self._selected_tag_filter = ""
                self.settings.save_active_tag_filter("")
            self.refresh_tag_filter_options()
            self.apply_filter(self.search_box.text())
            refresh_list()
            self.status_bar.showMessage(f"Deleted tag {tag_name}.")

        add_button.clicked.connect(add_tag)
        delete_button.clicked.connect(delete_tag)
        close_button.clicked.connect(dialog.accept)
        refresh_list()
        dialog.exec()

    def _prompt_for_tag(self, title: str) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        combo = QComboBox(dialog)
        combo.setEditable(True)
        combo.setMinimumWidth(scale_px(260, self))
        combo.addItems(self._all_known_tags())
        if combo.lineEdit() is not None:
            combo.lineEdit().setPlaceholderText("Select or type a tag")
        layout.addWidget(combo)

        buttons_row = QHBoxLayout()
        ok_button = QPushButton("OK", dialog)
        cancel_button = QPushButton("Cancel", dialog)
        buttons_row.addStretch(1)
        buttons_row.addWidget(ok_button)
        buttons_row.addWidget(cancel_button)
        layout.addLayout(buttons_row)

        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        combo.setFocus()
        combo.showPopup()

        if dialog.exec() != QDialog.Accepted:
            return ""
        return normalize_tag_name(combo.currentText())

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
        self.status_bar.showMessage("Workflow preset loaded.")

    def _image_size_filter_changed(self, _index: int) -> None:
        self.settings.save_image_size_filter(self.image_size_filter_box.currentText())
        self.apply_filter(self.search_box.text())

    def _restore_image_size_filter(self) -> None:
        stored_label = self.settings.load_image_size_filter()
        for index in range(self.image_size_filter_box.count()):
            if self.image_size_filter_box.itemText(index) == stored_label:
                self.image_size_filter_box.setCurrentIndex(index)
                return

    def _ensure_size_filter_dimensions(self) -> None:
        selected = self.image_size_filter_box.currentData()
        if selected is None:
            self._cancel_size_filter_worker()
            self._size_filter_pending = False
            return

        missing_items = [
            item
            for item in self.items
            if not item.is_video
            and not item.is_model
            and "dimensions" not in item.metadata
            and item.metadata.get("dimensions_error") != "1"
        ]
        if not missing_items:
            self._size_filter_pending = False
            return
        if self.current_size_filter is not None:
            return

        self._size_filter_token += 1
        token = self._size_filter_token
        worker = SizeFilterWorker(token, missing_items)
        worker.signals.progress.connect(self.status_bar.showMessage)
        worker.signals.finished.connect(self._size_filter_finished)
        worker.signals.error.connect(self._size_filter_failed)
        self.current_size_filter = worker
        self._size_filter_pending = True
        self.status_bar.showMessage(f"Reading image sizes... 0/{len(missing_items)}")
        self.size_pool.start(worker)

    def _cancel_size_filter_worker(self) -> None:
        self._size_filter_token += 1
        if self.current_size_filter is not None:
            self.current_size_filter.cancel()
            self.current_size_filter = None

    def _size_filter_finished(self, token: int, dimensions_by_path: dict, failed_paths: list) -> None:
        if token != self._size_filter_token:
            return
        self.current_size_filter = None
        failed = set(failed_paths)
        for item in self.items:
            path_key = str(item.preview_path)
            dimensions = dimensions_by_path.get(path_key)
            if dimensions is not None:
                item.metadata["dimensions"] = dimensions
                item.metadata.pop("dimensions_error", None)
            elif path_key in failed:
                item.metadata["dimensions_error"] = "1"
        self._size_filter_pending = False
        self._apply_grid_filter(self.search_box.text())
        self.status_bar.showMessage(f"Found {self.grid.visible_count()} items")

    def _size_filter_failed(self, token: int, message: str) -> None:
        if token != self._size_filter_token:
            return
        self.current_size_filter = None
        self._size_filter_pending = False
        self.status_bar.showMessage(f"Image size filter failed: {message}")

    def _tag_csv_export_finished(self, output_path: str, row_count: int, skipped_count: int) -> None:
        self.current_tag_export = None
        skipped_suffix = f" ({skipped_count} skipped)" if skipped_count else ""
        self.status_bar.showMessage(f"Exported {row_count} material set(s) to {output_path}{skipped_suffix}")

    def _tag_csv_export_failed(self, message: str) -> None:
        self.current_tag_export = None
        QMessageBox.warning(self, "CSV Export Error", message)
        self.status_bar.showMessage("Tag CSV export failed")

    def _schedule_search_filter(self, _text: str = "") -> None:
        self._search_filter_timer.start()

    def apply_filter(self, text: str) -> None:
        if self._using_favorites_search():
            if not self._ensure_favorites_items():
                return
        elif self.items is not self._folder_items:
            self._restore_folder_items()
        self._ensure_size_filter_dimensions()
        self._apply_grid_filter(text)

    def _apply_grid_filter(self, text: str, show_status: bool = True) -> None:
        self.grid.apply_filter(text, self.extension_filter_box.text(), self._combined_filter_predicate())
        self.request_visible_thumbnails()
        self.update_selected_info()
        if show_status:
            self.status_bar.showMessage(f"Found {self.grid.visible_count()} items")

    def _prime_grid_filter_settings(self) -> None:
        self.grid.apply_filter(
            self.search_box.text(),
            self.extension_filter_box.text(),
            self._combined_filter_predicate(),
        )

    def _workflow_text_changed(self, _text: str) -> None:
        if self.workflow_filter_checkbox.isChecked():
            self._schedule_search_filter()

    def _combined_filter_predicate(self):
        size_predicate = self._size_filter_predicate()
        workflow_predicate = (
            workflow_filter_predicate(self.naming_convention_box.text())
            if self.workflow_filter_checkbox.isChecked()
            else None
        )
        active_tag = self._active_tag_name()
        duplicate_hidden_keys = self._duplicate_hidden_keys if self.hide_duplicates_checkbox.isChecked() else None
        if (
            size_predicate is None
            and workflow_predicate is None
            and duplicate_hidden_keys is None
            and active_tag is None
        ):
            return None

        def predicate(media_item) -> bool:
            if duplicate_hidden_keys is not None and self._item_duplicate_key(media_item) in duplicate_hidden_keys:
                return False
            if active_tag is not None and not self._item_has_active_tag(media_item):
                return False
            if size_predicate is not None and not size_predicate(media_item):
                return False
            if workflow_predicate is not None and not workflow_predicate(media_item):
                return False
            return True

        return predicate

    def _active_tag_name(self) -> str | None:
        tag_name = normalize_tag_name(self._selected_tag_filter)
        if tag_name:
            return tag_name
        return None

    def _tag_filter_changed(self) -> None:
        tag_name = self.tag_filter_box.currentData()
        self._selected_tag_filter = normalize_tag_name(tag_name if isinstance(tag_name, str) else "")
        self.settings.save_active_tag_filter(self._selected_tag_filter)
        self._rebuild_tag_filter_lookup()
        self.apply_filter(self.search_box.text())

    def refresh_tag_filter_options(self) -> None:
        current_tag = self._active_tag_name()
        tags = self._all_tags_for_current_context()
        if current_tag and not any(tag_name.lower() == current_tag.lower() for tag_name in tags):
            tags.append(current_tag)
            tags.sort(key=str.lower)
        self.tag_filter_box.blockSignals(True)
        self.tag_filter_box.clear()
        self.tag_filter_box.addItem(ANY_TAG_LABEL, None)
        selected_index = 0
        for tag_name in tags:
            self.tag_filter_box.addItem(tag_name, tag_name)
            if current_tag and tag_name.lower() == current_tag.lower():
                selected_index = self.tag_filter_box.count() - 1
        self.tag_filter_box.setCurrentIndex(selected_index)
        self.tag_filter_box.blockSignals(False)
        self._rebuild_tag_filter_lookup()

    def _all_tags_for_current_context(self) -> list[str]:
        return self._all_tags_for_roots(self._tag_roots_for_current_context(existing_only=True))

    def _all_known_tags(self) -> list[str]:
        roots: list[Path] = []
        seen: set[Path] = set()
        for root in self._tag_roots_for_current_context(existing_only=True):
            if root not in seen:
                seen.add(root)
                roots.append(root)
        for favorite in self.favorites:
            root = self._tag_root_for_path(favorite, create=False)
            if root is None:
                continue
            resolved = root.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append(resolved)
        if self.current_root is not None:
            root = self._tag_root_for_path(self.current_root, create=False)
            if root is not None:
                resolved = root.resolve()
                if resolved not in seen:
                    roots.append(resolved)
        return self._all_tags_for_roots(roots)

    def _all_tags_for_roots(self, roots: list[Path]) -> list[str]:
        tags: dict[str, str] = {}
        for root in roots:
            try:
                for tag_name in TagStore(root).list_tags():
                    normalized = normalize_tag_name(tag_name)
                    if not normalized:
                        continue
                    tags.setdefault(normalized.lower(), normalized)
            except OSError:
                continue
        return sorted(tags.values(), key=str.lower)

    def _rebuild_tag_filter_lookup(self) -> None:
        self._tag_filter_lookup = {}
        self._tagged_item_keys = set()
        tag_name = self._active_tag_name()
        if tag_name is None:
            return
        for root in self._tag_roots_for_current_context(existing_only=True):
            try:
                tagged_paths = TagStore(root).tagged_paths(tag_name)
            except OSError:
                continue
            if tagged_paths:
                self._tag_filter_lookup[root.resolve()] = tagged_paths
        self._rebuild_tagged_item_keys(self.items)

    def _item_has_active_tag(self, item) -> bool:
        return self._item_duplicate_key(item) in self._tagged_item_keys

    def _rebuild_tagged_item_keys(self, items: list) -> None:
        self._tagged_item_keys = set()
        self._record_tagged_item_keys(items)

    def _record_tagged_item_keys(self, items: list) -> None:
        if not self._tag_filter_lookup:
            return
        tag_roots = list(self._tag_filter_lookup.items())
        for item in items:
            for root, tagged_paths in tag_roots:
                relative_path = self._relative_item_path(item, root)
                if relative_path is not None and relative_path in tagged_paths:
                    self._tagged_item_keys.add(self._item_duplicate_key(item))
                    break

    def _tag_roots_for_current_context(self, existing_only: bool = False) -> list[Path]:
        raw_roots = self._selected_favorites() if self._using_favorites_search() else []
        if not raw_roots and self.current_root is not None:
            raw_roots = [self.current_root]

        roots: list[Path] = []
        seen: set[Path] = set()
        for root in raw_roots:
            tag_root = self._tag_root_for_path(root, create=False) or root
            resolved = tag_root.resolve()
            if resolved in seen:
                continue
            if existing_only and not tag_database_exists(resolved):
                continue
            seen.add(resolved)
            roots.append(resolved)
        return roots

    def _tag_roots_for_manager(self) -> list[Path]:
        roots = self._tag_roots_for_current_context(existing_only=False)
        if roots:
            return roots
        if self.current_root is not None:
            return [self.current_root.resolve()]
        return []

    def _tag_root_for_item(self, item, create: bool) -> Path | None:
        existing_root = find_library_cache_root(item.preview_path)
        if existing_root is not None and (create or tag_database_exists(existing_root)):
            return existing_root.resolve()

        candidates: list[Path] = []
        if self.current_root is not None:
            candidates.append(self.current_root)
        candidates.extend(self._selected_favorites())
        for candidate in candidates:
            resolved = candidate.resolve()
            if self._relative_item_path(item, resolved) is not None:
                if create or tag_database_exists(resolved):
                    return resolved

        return item.folder.resolve() if create else None

    def _tag_root_for_path(self, path: Path, create: bool) -> Path | None:
        existing_root = find_library_cache_root(path)
        if existing_root is not None and (create or tag_database_exists(existing_root)):
            return existing_root.resolve()
        resolved = path.resolve()
        if create or tag_database_exists(resolved):
            return resolved
        return None

    def _relative_item_path(self, item, root: Path) -> str | None:
        try:
            return str(item.preview_path.relative_to(root)).replace("\\", "/")
        except (OSError, ValueError):
            try:
                return str(item.preview_path.resolve().relative_to(root.resolve())).replace("\\", "/")
            except (OSError, ValueError):
                return None

    def _reset_duplicate_filter_state(self) -> None:
        self._duplicate_first_keys = {}
        self._duplicate_hidden_keys = set()

    def _rebuild_duplicate_filter_state(self, items: list) -> None:
        self._reset_duplicate_filter_state()
        self._record_duplicate_items(items)

    def _record_duplicate_items(self, items: list) -> None:
        for item in items:
            name_key = self._duplicate_name_key(item)
            item_key = self._item_duplicate_key(item)
            if name_key in self._duplicate_first_keys:
                self._duplicate_hidden_keys.add(item_key)
                continue
            self._duplicate_first_keys[name_key] = item_key

    def _duplicate_name_key(self, item) -> str:
        return Path(item.display_name).stem.lower()

    def _item_duplicate_key(self, item) -> tuple[Path, str]:
        return (item.preview_path, item.display_name)

    def _size_filter_predicate(self):
        selected = self.image_size_filter_box.currentData()
        if selected is None:
            return None

        def predicate(media_item) -> bool:
            if media_item.is_video or media_item.is_model:
                return True
            dimensions = self._cached_image_dimensions_for_item(media_item)
            if dimensions is None:
                return self._size_filter_pending and media_item.metadata.get("dimensions_error") != "1"
            longest_side = max(dimensions)
            mode, limit = selected
            if mode == "min":
                return longest_side >= int(limit)
            return longest_side <= int(limit)

        return predicate

    def _cached_image_dimensions_for_item(self, item) -> tuple[int, int] | None:
        cached = item.metadata.get("dimensions")
        if isinstance(cached, str) and "x" in cached:
            try:
                width_text, height_text = cached.split("x", 1)
                return (int(width_text), int(height_text))
            except ValueError:
                return None
        return None

    def _favorites_search_toggled(self, checked: bool) -> None:
        self.refresh_tag_filter_options()
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
        return tuple(sorted(str(path.resolve()) for path in self._selected_favorites()))

    def _selected_favorites(self) -> list[Path]:
        return [path for path in self.favorites if path in self.favorite_search_enabled and path.exists()]

    def _ensure_favorites_items(self) -> bool:
        if not self.favorites:
            self._favorite_items = []
            self._favorite_index_ready = True
            self._favorite_index_signature = ()
            self._show_items([])
            self.status_bar.showMessage("Add folders to Favorites first.")
            return True
        if not self._selected_favorites():
            self._favorite_items = []
            self._favorite_index_ready = True
            self._favorite_index_signature = ()
            self._show_items([])
            self.status_bar.showMessage("Check at least one favorite to search it.")
            return True

        signature = self._favorite_signature()
        if self._favorite_index_ready and signature == self._favorite_index_signature:
            if self.items is not self._favorite_items:
                self._show_items(self._favorite_items)
            return True

        if self.current_favorites_index is not None:
            self.status_bar.showMessage("Loading favorites index...")
            return False

        worker = FavoritesIndexWorker(
            self._selected_favorites(),
            self.favorites_index_store,
            self.sequence_grouping_enabled,
        )
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
        self.refresh_tag_filter_options()
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

    def _show_items(self, items: list, fast: bool = False) -> None:
        self._prefetch_timer.stop()
        self._reset_thumbnail_queue()
        self._cancel_size_filter_worker()
        self._size_filter_pending = False
        self.items = items
        self._rebuild_duplicate_filter_state(items)
        self._rebuild_tagged_item_keys(items)
        self.grid.set_items(items, batch_size=5000 if fast else None)
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

    def _image_dimensions_for_item(self, item) -> tuple[int, int] | None:
        return media_dimensions(item.preview_path, item.metadata)

    def _image_dimensions_label(self, path: Path) -> str:
        dimensions = media_dimensions(path)
        if dimensions is None:
            return ""
        return f"{dimensions[0]} x {dimensions[1]} px"

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
            self.favorite_search_enabled.add(path)
            self.settings.save_favorites_search_enabled(list(self.favorite_search_enabled))
            self.folder_browser.set_favorites(self.favorites, self.favorite_search_enabled)
            self._favorite_index_ready = False
            self._favorite_index_signature = ()
            self.refresh_tag_filter_options()

    def remove_favorite(self, path: Path) -> None:
        self.favorites = [favorite for favorite in self.favorites if favorite != path]
        self.favorite_search_enabled.discard(path)
        self.settings.save(self.favorites)
        self.settings.save_favorites_search_enabled(list(self.favorite_search_enabled))
        self.folder_browser.set_favorites(self.favorites, self.favorite_search_enabled)
        self._favorite_items = [
            item
            for item in self._favorite_items
            if not (item.folder == path or path in item.folder.parents)
        ]
        self._favorite_index_ready = False
        self._favorite_index_signature = ()
        self.refresh_tag_filter_options()
        if self._using_favorites_search():
            self.apply_filter(self.search_box.text())

    def set_favorite_search_enabled(self, path: Path, enabled: bool) -> None:
        if enabled:
            self.favorite_search_enabled.add(path)
        else:
            self.favorite_search_enabled.discard(path)
        self.settings.save_favorites_search_enabled(list(self.favorite_search_enabled))
        self._favorite_index_ready = False
        self._favorite_index_signature = ()
        self.refresh_tag_filter_options()
        if self._using_favorites_search():
            self.apply_filter(self.search_box.text())

    def set_sequence_grouping_enabled(self, enabled: bool) -> None:
        self.sequence_grouping_enabled = enabled
        self.settings.save_sequence_grouping_enabled(enabled)
        self._favorite_index_ready = False
        self._favorite_index_signature = ()
        if self._using_favorites_search():
            self._show_items([])
            self.apply_filter(self.search_box.text())
            return
        if self.current_root is not None and self.current_root.exists() and not is_drive_root(self.current_root):
            self._show_items([])
            self.select_folder(self.current_root)

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
        if open_folder(path):
            self.status_bar.showMessage(f"Opened folder: {path}")
        else:
            self.status_bar.showMessage(f"Could not open folder: {path}")

    def open_viewer(self, item) -> None:
        if item.is_video:
            if open_video_in_vlc(item.preview_path):
                self.status_bar.showMessage(f"Opening in VLC: {item.preview_path.name}")
            elif open_with_default_app(item.preview_path):
                self.status_bar.showMessage(
                    f"Opening in default video player: {item.preview_path.name}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "VLC Not Found",
                    f"VLC could not be found. {vlc_install_hint()}",
                )
            return

        if item.is_model:
            viewer_name = open_model_in_viewer(item.preview_path)
            if viewer_name:
                self.status_bar.showMessage(f"Opening FBX in {viewer_name}: {item.preview_path.name}")
            else:
                QMessageBox.warning(
                    self,
                    "FBX Viewer Not Found",
                    f"No FBX viewer could be found. {fbx_handler_hint()}",
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
            self.status_bar.showMessage("No workflow textures found.")
            return

        current_index = 0
        for index, associated_item in enumerate(associated_items):
            if associated_item.preview_path == item.preview_path and associated_item.display_name == item.display_name:
                current_index = index
                break

        self.status_bar.showMessage(f"Showing {len(associated_items)} workflow texture(s).")
        self._show_selection_browser(
            associated_items,
            current_index,
            "Workflow Textures",
            "workflow texture(s)",
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

    def open_material_set_viewer(self, item) -> None:
        texture_set = texture_set_for_item(item, self.items)
        if not texture_set.items:
            self.status_bar.showMessage("No material set found.")
            return

        current_index = self._current_index_in_items(texture_set.items, item)
        self.status_bar.showMessage(f"Showing {len(texture_set.items)} material set file(s).")
        self._show_selection_browser(
            texture_set.items,
            current_index,
            "Material Set",
            "material set file(s)",
        )

    def open_selected_material_renderer(self) -> None:
        item = self._focused_media_item()
        if item is None:
            self.status_bar.showMessage("Select a texture first.")
            return
        if item.is_video or item.is_model:
            self.status_bar.showMessage("Material preview works on image textures.")
            return
        self.open_material_renderer(item)

    def open_material_renderer(self, item) -> None:
        texture_set = texture_set_for_item(item, self.items)
        opened, message = launch_material_renderer(texture_set)
        self.status_bar.showMessage(message)
        if not opened:
            QMessageBox.warning(self, "Material Renderer", message)

    def open_texture_validation(self, item) -> None:
        texture_set = texture_set_for_item(item, self.items)
        issues = validate_texture_set(texture_set)
        dialog = TextureSetValidationDialog(texture_set, issues, self)
        self.status_bar.showMessage(f"Validated {len(texture_set.items)} material set file(s).")
        self._show_tool_window(dialog)

    def open_channel_inspector(self, item) -> None:
        if item.is_video or item.is_model:
            self.status_bar.showMessage("Channel inspector works on image textures.")
            return

        dialog = ChannelInspectorDialog(item, self)
        self.status_bar.showMessage(f"Inspecting channels: {item.display_name}")
        self._show_tool_window(dialog)

    def _current_index_in_items(self, items: list, selected_item) -> int:
        for index, media_item in enumerate(items):
            if media_item.preview_path == selected_item.preview_path and media_item.display_name == selected_item.display_name:
                return index
        return 0

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
            self.naming_convention_box.text(),
        )
        browser.setModal(False)
        browser.setAttribute(Qt.WA_DeleteOnClose, True)
        browser.finished.connect(lambda _result, dialog=browser: self._forget_selection_window(dialog))
        self._selection_windows.append(browser)
        browser.show()

    def _forget_selection_window(self, dialog: AssociatedBrowserDialog) -> None:
        if dialog in self._selection_windows:
            self._selection_windows.remove(dialog)

    def _show_tool_window(self, dialog: QDialog) -> None:
        while len(self._tool_windows) >= 6:
            oldest = self._tool_windows.pop(0)
            oldest.close()

        dialog.setModal(False)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _object=None, window=dialog: self._forget_tool_window(window))
        self._tool_windows.append(dialog)
        dialog.show()

    def _forget_tool_window(self, dialog: QDialog) -> None:
        if dialog in self._tool_windows:
            self._tool_windows.remove(dialog)

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
        if self._loading_cached_folder:
            self.status_bar.showMessage(f"Loading cached folder... {added_count}/{total_count}")
        elif self.current_scan is None:
            self.status_bar.showMessage(f"Preparing items... {added_count}/{total_count}")
        if self.current_scan is not None and added_count > 500:
            return
        if added_count <= self.grid.total_count():
            self.request_visible_thumbnails()

    def _handle_population_finished(self, visible_count: int) -> None:
        self.request_visible_thumbnails()
        if self._loading_cached_folder:
            self._loading_cached_folder = False
            self.status_bar.showMessage(f"Loaded cached folder. Found {visible_count} items")
            return
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
    # Load-bearing identity strings: they determine the QStandardPaths
    # app-data location (thumbnail cache) for existing installs. The
    # QSettings("TextureBrowser", "TextureBrowser") store in favorites.py
    # is intentionally separate; do not "unify" either without migration.
    app.setApplicationName("Texture Browser")
    app.setApplicationVersion(application_version())
    app.setOrganizationName("TextureBrowser")
    app.setDesktopFileName("texturebrowser")
    icon = app_icon()
    app.setWindowIcon(icon)
    app.setStyle("Fusion")
    apply_theme(app, FavoritesStore().load_theme_mode())

    startup_screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    startup_splash = create_splash("Loading Texture Browser...", startup_screen)
    if startup_splash is not None:
        startup_splash.show()
        app.processEvents()

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    if startup_splash is not None:
        QTimer.singleShot(3000, startup_splash.close)
    sys.exit(app.exec())
