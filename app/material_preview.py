from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPixmap, QRadialGradient

from app.models import MediaItem
from app.texture_sets import TextureSet, texture_set_for_item


MATERIAL_PREVIEW_VERSION = 2
RELEVANT_ROLES = {
    "ao",
    "basecolor",
    "emissive",
    "gloss",
    "height",
    "metallic",
    "normal",
    "opacity",
    "packed",
    "roughness",
    "specular",
}
ROLE_BADGES = {
    "basecolor": "BC",
    "normal": "N",
    "roughness": "R",
    "metallic": "M",
    "ao": "AO",
    "packed": "PK",
    "height": "H",
    "gloss": "G",
    "specular": "S",
}


@dataclass(slots=True)
class MaterialPreviewSpec:
    texture_set: TextureSet
    cache_key: str
    primary_paths: dict[str, Path]
    packed_layout: str | None
    directx_normal: bool


def material_preview_spec(seed: MediaItem, candidates: list[MediaItem] | None = None) -> MaterialPreviewSpec | None:
    if seed.is_video or seed.is_model:
        return None

    texture_set = texture_set_for_item(seed, candidates or [seed])
    if len(texture_set.items) < 2:
        return None

    primary_paths: dict[str, Path] = {}
    for role, items in texture_set.roles.items():
        if role in RELEVANT_ROLES and items:
            primary_paths[role] = items[0].preview_path

    if not primary_paths:
        return None
    if "basecolor" not in primary_paths and "normal" not in primary_paths and "packed" not in primary_paths:
        return None

    normal_path = primary_paths.get("normal")
    directx_normal = False
    if normal_path is not None:
        normal_name = normal_path.stem.lower()
        directx_normal = "directx" in normal_name or re.search(r"(^|[_\-.])dx($|[_\-.])", normal_name) is not None

    packed_layout = None
    packed_path = primary_paths.get("packed")
    if packed_path is not None:
        packed_layout = _packed_layout_from_name(packed_path.stem)

    return MaterialPreviewSpec(
        texture_set=texture_set,
        cache_key=_preview_cache_key(primary_paths),
        primary_paths=primary_paths,
        packed_layout=packed_layout,
        directx_normal=directx_normal,
    )


def render_material_preview(spec: MaterialPreviewSpec, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#1e2024"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    _draw_background(painter, size)
    _draw_material_sphere(painter, spec, size)
    _draw_role_badges(painter, spec, size)

    painter.end()
    return pixmap


def _preview_cache_key(primary_paths: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    digest.update(f"material-preview-v{MATERIAL_PREVIEW_VERSION}".encode("utf-8"))
    for role, path in sorted(primary_paths.items()):
        try:
            stat = path.stat()
            payload = f"{role}|{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
        except OSError:
            payload = f"{role}|{path.resolve()}"
        digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _packed_layout_from_name(stem: str) -> str | None:
    normalized = re.sub(r"[^a-z]", "", stem.lower())
    for layout in ("orm", "arm", "mro", "rma", "mra", "rao"):
        if layout in normalized:
            return layout
    return "orm"


def _draw_background(painter: QPainter, size: int) -> None:
    painter.fillRect(0, 0, size, size, QColor("#20242a"))
    painter.setPen(QColor("#333943"))
    painter.drawRect(0, 0, size - 1, size - 1)


def _draw_material_sphere(painter: QPainter, spec: MaterialPreviewSpec, size: int) -> None:
    badge_band = max(22, size // 5)
    margin = max(8, size // 12)
    sphere_size = max(24, min(size - margin * 2, size - badge_band - margin))
    x = (size - sphere_size) // 2
    y = max(margin // 2, (size - badge_band - sphere_size) // 2)
    sphere_rect = QRectF(x, y, sphere_size, sphere_size)

    base_path = (
        spec.primary_paths.get("basecolor")
        or spec.primary_paths.get("normal")
        or spec.primary_paths.get("packed")
        or next(iter(spec.primary_paths.values()))
    )
    image = _load_preview_image(base_path, sphere_size)

    path = QPainterPath()
    path.addEllipse(sphere_rect)
    painter.save()
    painter.setClipPath(path)
    if image is not None and not image.isNull():
        painter.drawImage(sphere_rect, image)
    else:
        painter.fillRect(sphere_rect, QColor("#8b8f98"))

    shadow = QRadialGradient(sphere_rect.center(), sphere_size * 0.65)
    shadow.setColorAt(0.0, QColor(255, 255, 255, 35))
    shadow.setColorAt(0.35, QColor(255, 255, 255, 8))
    shadow.setColorAt(0.72, QColor(0, 0, 0, 28))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 125))
    painter.fillRect(sphere_rect, shadow)

    highlight = QRadialGradient(
        sphere_rect.left() + sphere_size * 0.32,
        sphere_rect.top() + sphere_size * 0.25,
        sphere_size * 0.42,
    )
    highlight.setColorAt(0.0, QColor(255, 255, 255, 92))
    highlight.setColorAt(0.32, QColor(255, 255, 255, 22))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(sphere_rect, highlight)
    painter.restore()

    painter.setPen(QColor(0, 0, 0, 120))
    painter.drawEllipse(sphere_rect.adjusted(0.5, 0.5, -0.5, -0.5))


def _draw_role_badges(painter: QPainter, spec: MaterialPreviewSpec, size: int) -> None:
    roles = [role for role in ROLE_BADGES if role in spec.primary_paths]
    if not roles:
        return

    label_count = min(len(roles), 5)
    gap = max(2, size // 48)
    badge_height = max(14, min(22, size // 7))
    total_width = size - gap * (label_count + 1)
    badge_width = max(12, total_width // label_count)
    y = size - badge_height - gap
    font = QFont("Segoe UI", max(6, min(9, size // 18)))
    font.setBold(True)
    painter.setFont(font)

    for index, role in enumerate(roles[:label_count]):
        rect = QRect(gap + index * (badge_width + gap), y, badge_width, badge_height)
        painter.fillRect(rect, _role_badge_color(role))
        painter.setPen(QColor("#f3f6fb"))
        painter.drawText(rect, Qt.AlignCenter, ROLE_BADGES[role])


def _role_badge_color(role: str) -> QColor:
    colors = {
        "basecolor": QColor("#2f7dd1"),
        "normal": QColor("#7f6eea"),
        "roughness": QColor("#737b84"),
        "metallic": QColor("#45515f"),
        "ao": QColor("#5f6f39"),
        "packed": QColor("#d3922f"),
        "height": QColor("#8a6a4a"),
        "gloss": QColor("#4da1a9"),
        "specular": QColor("#5f90c8"),
    }
    return colors.get(role, QColor("#4c5662"))


def _load_preview_image(path: Path, size: int) -> QImage | None:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    original_size = reader.size()
    if original_size.isValid():
        reader.setScaledSize(original_size.scaled(size, size, Qt.KeepAspectRatioByExpanding))
    image = reader.read()
    if image.isNull():
        return None
    return _center_crop(image, size, size)


def _center_crop(image: QImage, width: int, height: int) -> QImage:
    if image.width() == width and image.height() == height:
        return image
    x = max(0, (image.width() - width) // 2)
    y = max(0, (image.height() - height) // 2)
    return image.copy(x, y, min(width, image.width()), min(height, image.height())).scaled(
        width,
        height,
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
