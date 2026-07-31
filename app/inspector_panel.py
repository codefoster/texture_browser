"""Right-hand inspector panel (mockup option 1c).

Pure-view widget: MainWindow feeds it plain values and listens to its
signals — no direct dependency on the app's models, so it drops in cleanly.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _kicker(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("variant", "kicker")
    return label


class InspectorPanel(QWidget):
    materialViewerRequested = Signal()
    seekRequested = Signal()
    revealRequested = Signal()
    validateRequested = Signal()
    addTagRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspectorPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(260)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- preview ---
        self.preview = QLabel()
        self.preview.setFixedHeight(210)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background: rgba(127,127,127,0.25);")
        root.addWidget(self.preview)

        # --- scrolling body ---
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(16, 14, 16, 14)
        self._body.setSpacing(10)

        self.name_label = QLabel("Select an item")
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-weight: 800; font-size: 14px;")
        self._body.addWidget(self.name_label)

        self._meta = QGridLayout()
        self._meta.setHorizontalSpacing(10)
        self._meta.setVerticalSpacing(6)
        self._meta.setColumnStretch(1, 1)
        self._body.addLayout(self._meta)

        self._body.addWidget(_kicker("TAGS"))
        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(6)
        self._body.addLayout(self._tags_row)

        self._body.addWidget(_kicker("TEXTURE SET"))
        self._set_rows = QVBoxLayout()
        self._set_rows.setSpacing(0)
        self._body.addLayout(self._set_rows)
        self._body.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        # --- actions ---
        actions = QWidget()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(16, 12, 16, 14)
        actions_layout.setSpacing(8)
        self.material_button = QPushButton("Open in Material Viewer")
        self.material_button.setProperty("variant", "primary")
        self.material_button.clicked.connect(self.materialViewerRequested)
        actions_layout.addWidget(self.material_button)
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, signal in (
            ("Seek", self.seekRequested),
            ("Reveal", self.revealRequested),
            ("Validate", self.validateRequested),
        ):
            button = QPushButton(text)
            button.clicked.connect(signal)
            row.addWidget(button, 1)
        actions_layout.addLayout(row)
        root.addWidget(actions)

    # ---- public API -------------------------------------------------

    def clear(self) -> None:
        self.preview.setPixmap(QPixmap())
        self.name_label.setText("Select an item")
        self._clear_layout(self._meta)
        self._clear_layout(self._tags_row)
        self._clear_layout(self._set_rows)
        self.material_button.setEnabled(False)

    def set_item(
        self,
        name: str,
        pixmap: QPixmap | None,
        meta: list[tuple[str, str]],
        tags: list[str],
        set_rows: list[tuple[str, str, bool]],  # (role, status, ok)
    ) -> None:
        self.material_button.setEnabled(True)
        self.name_label.setText(name)
        if pixmap is not None and not pixmap.isNull():
            self.preview.setPixmap(
                pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.preview.setPixmap(QPixmap())

        self._clear_layout(self._meta)
        for row, (key, value) in enumerate(meta):
            key_label = QLabel(key.upper())
            key_label.setStyleSheet("font-size: 10px; font-weight: 800; color: #7d7979;")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._meta.addWidget(key_label, row, 0, Qt.AlignTop)
            self._meta.addWidget(value_label, row, 1)

        self._clear_layout(self._tags_row)
        for tag in tags:
            chip = QLabel(tag)
            chip.setStyleSheet("border: 1px solid #7d7979; padding: 2px 8px; font-size: 11px;")
            self._tags_row.addWidget(chip)
        add = QPushButton("+ Add")
        add.setProperty("variant", "link")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.addTagRequested)
        self._tags_row.addWidget(add)
        self._tags_row.addStretch(1)

        self._clear_layout(self._set_rows)
        for role, status, ok in set_rows:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 5, 0, 5)
            role_label = QLabel(role)
            role_label.setStyleSheet("font-weight: 600;")
            status_label = QLabel(status.upper())
            status_label.setStyleSheet(
                "font-size: 10px; font-weight: 800; color: %s;"
                % ("#7d7979" if ok else "#ec3013")
            )
            row_layout.addWidget(role_label, 1)
            row_layout.addWidget(status_label)
            self._set_rows.addWidget(row_widget)

    # ---- helpers ----------------------------------------------------

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            entry = layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
