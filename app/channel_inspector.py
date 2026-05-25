from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.models import MediaItem
from app.thumbnailer import load_media_qimage
from app.utils import scale_px


class ChannelInspectorDialog(QDialog):
    def __init__(self, item: MediaItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Channel Inspector")
        self.resize(scale_px(900, self), scale_px(700, self))

        layout = QVBoxLayout(self)
        title = QLabel(item.display_name)
        title.setStyleSheet("QLabel { color: #f2f5f8; font-weight: 600; }")
        layout.addWidget(title)

        image = load_media_qimage(item, scale_px(768, self))
        if image is None or image.isNull():
            layout.addWidget(QLabel("This file could not be loaded as an image."))
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(scale_px(8, self), scale_px(8, self), scale_px(8, self), scale_px(8, self))
        grid.setSpacing(scale_px(12, self))

        red_label, green_label, blue_label = _packed_channel_labels(item)
        panels = [
            ("RGB", image),
            (red_label, _channel_image(image, 0)),
            (green_label, _channel_image(image, 1)),
            (blue_label, _channel_image(image, 2)),
        ]
        if image.hasAlphaChannel():
            panels.append(("Alpha", _channel_image(image, 3)))

        for index, (label, panel_image) in enumerate(panels):
            grid.addWidget(_image_panel(label, panel_image, self), index // 2, index % 2)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)


def _image_panel(title: str, image: QImage, parent: QWidget) -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(title)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("QLabel { color: #dbe6f3; font-weight: 600; }")
    preview = QLabel()
    preview.setAlignment(Qt.AlignCenter)
    preview.setMinimumSize(scale_px(280, parent), scale_px(220, parent))
    preview.setPixmap(QPixmap.fromImage(image))
    preview.setStyleSheet("QLabel { background: #1e1f22; border: 1px solid #424851; }")
    layout.addWidget(label)
    layout.addWidget(preview)
    return panel


def _channel_image(source: QImage, channel_index: int) -> QImage:
    image = source.convertToFormat(QImage.Format_RGBA8888)
    output = QImage(image.width(), image.height(), QImage.Format_RGB888)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if channel_index == 0:
                value = color.red()
            elif channel_index == 1:
                value = color.green()
            elif channel_index == 2:
                value = color.blue()
            else:
                value = color.alpha()
            output.setPixelColor(x, y, QColor(value, value, value))
    return output


def _packed_channel_labels(item: MediaItem) -> tuple[str, str, str]:
    stem = re.sub(r"[^a-z0-9]+", " ", item.preview_path.stem.lower())
    compact = re.sub(r"[^a-z0-9]+", "", item.preview_path.stem.lower())
    tokens = set(stem.split())
    if "orm" in tokens or "orm" in compact:
        return ("Red: Occlusion", "Green: Roughness", "Blue: Metallic")
    if "mro" in tokens or "mro" in compact:
        return ("Red: Metallic", "Green: Roughness", "Blue: Occlusion")
    if "rma" in tokens or "rma" in compact:
        return ("Red: Roughness", "Green: Metallic", "Blue: Occlusion")
    if "arm" in tokens or "arm" in compact:
        return ("Red: Occlusion", "Green: Roughness", "Blue: Metallic")
    return ("Red", "Green", "Blue")
