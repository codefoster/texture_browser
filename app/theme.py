"""Modernist theme for Texture Browser (dark + light).

Flat, architectural: Archivo everywhere, zero corner radius, 2px rules,
one red accent (#ec3013). Matches the approved HTML mockups.

Usage (in main.py, right after creating QApplication):

    from app.theme import apply_theme
    apply_theme(app, "dark")   # or "light"
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

ACCENT = "#ec3013"
ACCENT_HOVER = "#dd2b0f"

DARK = {
    "window": "#201e1d",      # main ground
    "panel": "#262423",       # sidebars / info strip
    "chrome": "#171615",      # titlebar-adjacent / status bar
    "input_bg": "#1b1a19",    # inputs + thumbnail grid viewport
    "border": "#454140",      # strong 2px rules
    "hair": "#383534",        # 1px row rules
    "text": "#f3f2f2",
    "sub": "#d6d2d0",
    "muted": "#7d7979",
    "hover": "#2f2c2b",
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "accent_text": "#ff9783", # accent-tinted text ON dark ground
    "kicker": "#ff563c",      # section labels (FAVORITES / FOLDERS / ...)
}

LIGHT = {
    "window": "#f3f2f2",
    "panel": "#eae9e9",
    "chrome": "#201e1d",      # status bar stays ink in light mode
    "input_bg": "#ffffff",
    "border": "#a6a3a1",
    "hair": "#d5d2d1",
    "text": "#201e1d",
    "sub": "#444141",
    "muted": "#7d7979",
    "hover": "#e2e0df",
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "accent_text": "#ae1800", # deep ramp step for small accent text on light
    "kicker": ACCENT,
}

_QSS = """
* { font-family: "Archivo", "Segoe UI", "Noto Sans", sans-serif; }

QMainWindow, QDialog, QMessageBox, QInputDialog { background: %(window)s; }
QWidget { color: %(text)s; }

/* ---- toolbar ---- */
QToolBar {
    background: %(window)s; border: none;
    border-bottom: 2px solid %(border)s;
    padding: 8px 12px; spacing: 8px;
}

/* ---- buttons: secondary by default, flush-left labels ---- */
QPushButton {
    background: transparent;
    border: 2px solid %(border)s;
    color: %(text)s;
    padding: 6px 14px;
    font-weight: 700;
    text-align: left;
    border-radius: 0;
}
QPushButton:hover { border-color: %(muted)s; background: %(hover)s; }
QPushButton:pressed { background: %(hover)s; }
QPushButton:checked { background: %(accent)s; border-color: %(accent)s; color: #ffffff; }
QPushButton:disabled { color: %(muted)s; border-color: %(hair)s; }
QPushButton:focus { outline: none; border-color: %(accent)s; }

QPushButton[variant="primary"] { background: %(accent)s; border: 2px solid %(accent)s; color: #ffffff; }
QPushButton[variant="primary"]:hover,
QPushButton[variant="primary"]:pressed { background: %(accent_hover)s; border-color: %(accent_hover)s; }

/* section-header link buttons (replaces the old blue flat buttons) */
QPushButton[variant="link"] {
    border: none; background: transparent; padding: 0;
    color: %(kicker)s; font-weight: 800;
}
QPushButton[variant="link"]:hover { color: %(accent_text)s; }

/* ---- inputs ---- */
QLineEdit, QComboBox {
    background: %(input_bg)s;
    border: 1px solid %(border)s;
    color: %(text)s;
    padding: 6px 10px;
    border-radius: 0;
    selection-background-color: %(accent)s;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid %(accent)s; }
QLineEdit:disabled, QComboBox:disabled { color: %(muted)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: %(panel)s; border: 1px solid %(border)s; color: %(text)s;
    selection-background-color: %(accent)s; selection-color: #ffffff; outline: 0;
}

/* ---- checkboxes: flat squares, accent fill when checked ---- */
QCheckBox { color: %(sub)s; spacing: 7px; font-weight: 600; background: transparent; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 2px solid %(border)s; background: transparent; border-radius: 0;
}
QCheckBox::indicator:hover { border-color: %(muted)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }

/* ---- trees / lists (folder tree, favorites, thumbnail grid) ---- */
QTreeWidget, QTreeView, QListWidget, QListView {
    background: %(panel)s; border: none; outline: 0;
}
QTreeView::item, QTreeWidget::item { padding: 4px 6px; }
QTreeView::item:hover, QTreeWidget::item:hover,
QListWidget::item:hover { background: %(hover)s; }
QTreeView::item:selected, QTreeWidget::item:selected,
QListWidget::item:selected, QListView::item:selected {
    background: %(accent)s; color: #ffffff;
}

/* the thumbnail grid viewport sits on the deepest ground */
QListWidget#thumbnailGrid, QListView#thumbnailGrid {
    background: %(input_bg)s; padding: 10px;
}
/* mockup selection style: outline, not fill */
QListWidget#thumbnailGrid::item:selected {
    background: transparent; border: 2px solid %(accent)s; color: %(text)s;
}
QListWidget#thumbnailGrid::item:hover { background: %(hover)s; }

/* ---- structure ---- */
QSplitter::handle { background: %(border)s; }
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }

QStatusBar { background: %(chrome)s; color: %(muted)s; border: none; }
QStatusBar::item { border: none; }

QLabel { background: transparent; }
QLabel[variant="kicker"] { color: %(kicker)s; font-weight: 800; }
QLabel[variant="info"] {
    background: %(panel)s; border: 1px solid %(hair)s;
    color: %(sub)s; padding: 8px 12px;
}

QHeaderView::section {
    background: %(panel)s; color: %(text)s; border: none;
    border-bottom: 2px solid %(border)s; padding: 6px; font-weight: 800;
}

/* ---- scrollbars: flat, no arrows ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:vertical { background: %(border)s; min-height: 24px; border-radius: 0; }
QScrollBar::handle:horizontal { background: %(border)s; min-width: 24px; border-radius: 0; }
QScrollBar::handle:hover { background: %(muted)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip {
    background: %(chrome)s; color: #f3f2f2;
    border: 1px solid %(border)s; padding: 4px 8px;
}

QMenu { background: %(panel)s; border: 1px solid %(border)s; }
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: %(accent)s; color: #ffffff; }
QMenu::separator { height: 1px; background: %(hair)s; margin: 4px 0; }
"""


def _fonts_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "fonts"


def load_fonts() -> None:
    """Register bundled Archivo faces (assets/fonts/Archivo-*.ttf)."""
    fonts = _fonts_dir()
    if fonts.is_dir():
        for path in sorted(fonts.glob("Archivo*.ttf")):
            QFontDatabase.addApplicationFont(str(path))


def build_qss(mode: str = "dark") -> str:
    return _QSS % (DARK if mode == "dark" else LIGHT)


def apply_theme(app: QApplication, mode: str = "dark") -> None:
    """Load fonts and apply the theme. Safe to call again to switch modes."""
    load_fonts()
    app.setStyleSheet(build_qss(mode))
    font = app.font()
    font.setFamily("Archivo")
    app.setFont(font)
