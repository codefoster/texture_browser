from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.utils import scale_px


class NamingPresetDialog(QDialog):
    presetApplied = Signal(str)
    presetsChanged = Signal(dict)

    def __init__(
        self,
        presets: dict[str, str],
        current_convention: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Naming Presets")
        self.resize(scale_px(620, self), scale_px(360, self))

        self.presets = dict(sorted(presets.items(), key=lambda item: item[0].lower()))
        self.current_convention = current_convention

        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(self._select_preset)
        self.preset_list.itemDoubleClicked.connect(lambda _item: self.apply_selected())

        self.name_box = QLineEdit()
        self.name_box.setPlaceholderText("Preset name")

        self.convention_box = QLineEdit()
        self.convention_box.setPlaceholderText("metallic, albedo, roughness, normal")

        new_button = QPushButton("New")
        save_button = QPushButton("Save")
        load_button = QPushButton("Load")
        delete_button = QPushButton("Delete")
        close_button = QPushButton("Close")

        new_button.clicked.connect(self.new_preset)
        save_button.clicked.connect(self.save_preset)
        load_button.clicked.connect(self.apply_selected)
        delete_button.clicked.connect(self.delete_selected)
        close_button.clicked.connect(self.accept)

        fields = QVBoxLayout()
        fields.addWidget(QLabel("Name"))
        fields.addWidget(self.name_box)
        fields.addWidget(QLabel("Naming convention"))
        fields.addWidget(self.convention_box)
        fields.addStretch(1)

        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(new_button)
        edit_buttons.addWidget(save_button)
        edit_buttons.addWidget(load_button)
        edit_buttons.addWidget(delete_button)
        edit_buttons.addStretch(1)
        edit_buttons.addWidget(close_button)

        body = QHBoxLayout()
        body.addWidget(self.preset_list, 1)
        body.addLayout(fields, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addLayout(edit_buttons)

        self._refresh_preset_list()
        self.new_preset()

    def new_preset(self) -> None:
        self.preset_list.clearSelection()
        self.name_box.clear()
        self.convention_box.setText(self.current_convention)
        self.name_box.setFocus(Qt.OtherFocusReason)

    def save_preset(self) -> None:
        name = self.name_box.text().strip()
        convention = self.convention_box.text().strip()
        if not name:
            QMessageBox.warning(self, "Preset Name Required", "Enter a preset name before saving.")
            return

        self.presets[name] = convention
        self.presets = dict(sorted(self.presets.items(), key=lambda item: item[0].lower()))
        self.presetsChanged.emit(dict(self.presets))
        self._refresh_preset_list(name)

    def apply_selected(self) -> None:
        convention = self.convention_box.text().strip()
        if not convention and self.name_box.text().strip() in self.presets:
            convention = self.presets[self.name_box.text().strip()]
        self.presetApplied.emit(convention)

    def delete_selected(self) -> None:
        name = self.name_box.text().strip()
        if not name or name not in self.presets:
            return

        del self.presets[name]
        self.presetsChanged.emit(dict(self.presets))
        self._refresh_preset_list()
        self.new_preset()

    def _select_preset(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        name = current.data(Qt.UserRole)
        if not isinstance(name, str):
            return
        self.name_box.setText(name)
        self.convention_box.setText(self.presets.get(name, ""))

    def _refresh_preset_list(self, selected_name: str | None = None) -> None:
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        for name in self.presets:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.preset_list.addItem(item)
            if name == selected_name:
                self.preset_list.setCurrentItem(item)
        self.preset_list.blockSignals(False)
        if selected_name and selected_name in self.presets:
            self.name_box.setText(selected_name)
            self.convention_box.setText(self.presets[selected_name])
