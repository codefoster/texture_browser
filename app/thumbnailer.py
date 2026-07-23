from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPen, QPixmap

from app.models import MediaItem
from app.utils import (
    IMAGE_EXTENSIONS,
    cache_dir,
    cache_key,
    ensure_library_cache,
    find_library_cache_dir,
    find_library_cache_root,
    library_manifest_path,
    load_library_manifest,
    save_library_manifest,
)

try:
    from PIL import Image, ImageOps, ImageSequence
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None
    ImageSequence = None

try:
    import imageio.v3 as iio
except ImportError:  # pragma: no cover
    iio = None

try:
    from psd_tools import PSDImage
except ImportError:  # pragma: no cover
    PSDImage = None

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

_manifest_cache: dict[Path, dict] = {}
_manifest_cache_lock = threading.RLock()
_memory_cache_lock = threading.RLock()
_memory_image_cache: OrderedDict[tuple[str, int, int, int], QImage] = OrderedDict()
_memory_cache_bytes = 0
_memory_cache_byte_limit = 96 * 1024 * 1024


class ThumbnailWorkerSignals(QObject):
    ready = Signal(int, str, int, QImage)
    status = Signal(str)


class ThumbnailWorker(QRunnable):
    def __init__(self, item: MediaItem, size: int, generation: int) -> None:
        super().__init__()
        self.item = item
        self.size = size
        self.generation = generation
        self.signals = ThumbnailWorkerSignals()

    def run(self) -> None:
        image = load_or_create_thumbnail(self.item, self.size, self.signals.status.emit)
        self.signals.ready.emit(self.generation, str(self.item.preview_path), self.size, image)


def load_or_create_thumbnail(item: MediaItem, size: int, status_callback=None) -> QImage:
    source_path = item.preview_path
    cache_path = None
    memory_key = _memory_cache_key(source_path, size)

    if memory_key is not None:
        image = _memory_cache_lookup(memory_key)
        if image is not None:
            return image

    try:
        manifest_candidate = _manifest_cache_path(source_path, size)
        candidate_paths: list[Path] = []
        if manifest_candidate is not None:
            candidate_paths.append(manifest_candidate)
        for candidate in _cache_candidates(source_path, size):
            if candidate not in candidate_paths:
                candidate_paths.append(candidate)
        for candidate in candidate_paths:
            if candidate.exists():
                image = QImage(str(candidate))
                if not image.isNull():
                    if memory_key is not None:
                        _remember_image(memory_key, image)
                    return image
        cache_path = _preferred_cache_path(source_path, size)
    except OSError:
        cache_path = None

    image = _generate_thumbnail(item, size)
    if cache_path is not None and not image.isNull():
        image.save(str(cache_path), "PNG")
    if memory_key is not None and not image.isNull():
        _remember_image(memory_key, image)
    if status_callback:
        status_callback(f"Generating thumbnails... {item.display_name}")
    return image


def preferred_cache_path_for(source_path: Path, size: int) -> Path:
    return _preferred_cache_path(source_path, size)


def rebuild_library_manifest(root: Path, items: list[MediaItem], sizes: list[int]) -> None:
    manifest = _load_manifest(root)
    entries = manifest.setdefault("entries", {})
    current_sizes = {str(size) for size in sizes}

    for item in items:
        source_path = item.preview_path
        try:
            relative_path = str(source_path.resolve().relative_to(root.resolve())).replace("\\", "/")
            stat = source_path.stat()
        except (OSError, ValueError):
            continue

        entry = entries.setdefault(relative_path, {})
        entry["mtime_ns"] = stat.st_mtime_ns
        entry["size"] = stat.st_size
        thumbs = entry.setdefault("thumbs", {})
        if not isinstance(thumbs, dict):
            thumbs = {}
            entry["thumbs"] = thumbs

        for size in sizes:
            cache_path = preferred_cache_path_for(source_path, size)
            if cache_path.exists():
                try:
                    thumbs[str(size)] = str(cache_path.resolve().relative_to(root.resolve())).replace("\\", "/")
                except ValueError:
                    thumbs[str(size)] = str(cache_path)
            else:
                thumbs.pop(str(size), None)

        if not any(size_key in thumbs for size_key in current_sizes):
            entries.pop(relative_path, None)

    _store_manifest(root, manifest)


def _cache_candidates(source_path: Path, size: int) -> list[Path]:
    candidates: list[Path] = []
    library_root = find_library_cache_root(source_path)
    library_dir = find_library_cache_dir(source_path)
    if library_dir is not None and library_root is not None:
        library_key = cache_key(source_path, library_root)
        candidates.append(library_dir / f"{library_key}_{size}.png")

    global_key = cache_key(source_path)
    candidates.append(cache_dir() / f"{global_key}_{size}.png")
    return candidates


def _preferred_cache_path(source_path: Path, size: int) -> Path:
    library_root = find_library_cache_root(source_path)
    library_dir = find_library_cache_dir(source_path)
    if library_dir is not None and library_root is not None:
        library_key = cache_key(source_path, library_root)
        return library_dir / f"{library_key}_{size}.png"

    parent_cache_dir = source_path.parent / ".texturebrowser-cache"
    if parent_cache_dir.exists():
        library_dir = ensure_library_cache(source_path.parent)
        library_key = cache_key(source_path, source_path.parent)
        return library_dir / f"{library_key}_{size}.png"

    global_key = cache_key(source_path)
    return cache_dir() / f"{global_key}_{size}.png"


def _generate_thumbnail(item: MediaItem, size: int) -> QImage:
    image = load_media_qimage(item, size)
    if image is None or image.isNull():
        return build_placeholder_image(item.extension or "file", size, item.is_video)

    scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("#1e1f22"))

    painter = QPainter(canvas)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawImage(x, y, scaled)
    if item.is_video:
        _draw_video_badge(painter, size)
    elif item.is_sequence:
        _draw_sequence_badge(painter, size)
    painter.end()
    return canvas


def load_media_qimage(item: MediaItem, target_size: int | None = None) -> QImage | None:
    path = item.preview_path
    ext = path.suffix.lower()

    try:
        if item.is_video:
            return _load_video_frame(path)
        if ext == ".psd" and PSDImage is not None:
            composite = PSDImage.open(path).composite()
            buffer = io.BytesIO()
            composite.save(buffer, format="PNG")
            image = QImage()
            image.loadFromData(buffer.getvalue(), "PNG")
            return image
        if ext in IMAGE_EXTENSIONS:
            image = _load_with_qimage_reader(path, target_size)
            if image is not None and not image.isNull():
                return image
        if Image is not None:
            try:
                with Image.open(path) as pil_image:
                    if getattr(pil_image, "is_animated", False) and ImageSequence is not None:
                        pil_image.seek(0)
                    pil_image = ImageOps.exif_transpose(pil_image) if ImageOps else pil_image
                    if target_size is not None:
                        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
                        pil_image.thumbnail((target_size, target_size), resampling)
                    if pil_image.mode not in ("RGB", "RGBA"):
                        pil_image = pil_image.convert("RGBA")
                    data = pil_image.tobytes("raw", "RGBA")
                    image = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
                    return image.copy()
            except Exception:
                pass
        if iio is not None:
            frame = iio.imread(path)
            if frame.ndim == 2:
                frame = frame[:, :, None]
            if frame.shape[2] == 1:
                frame = frame.repeat(3, axis=2)
            if frame.shape[2] >= 3:
                frame = frame[:, :, :3]
            if frame.dtype != "uint8":
                frame = _normalize_to_uint8(frame)
            height, width, channels = frame.shape
            fmt = QImage.Format_RGB888 if channels == 3 else QImage.Format_RGBA8888
            image = QImage(frame.data, width, height, frame.strides[0], fmt)
            return image.copy()
        image = QImage(str(path))
        return image if not image.isNull() else None
    except Exception:
        return None


def _normalize_to_uint8(frame):
    import numpy as np

    frame = frame.astype("float32")
    max_value = frame.max()
    min_value = frame.min()
    if max_value == min_value:
        return np.zeros_like(frame, dtype="uint8")
    normalized = (frame - min_value) / (max_value - min_value)
    return (normalized * 255).clip(0, 255).astype("uint8")


def _load_video_frame(path: Path) -> QImage | None:
    if cv2 is None:
        image = QImage(str(path))
        return image if not image.isNull() else None

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return None
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target_frame = max(0, int(frame_count * 0.1) - 1)
    capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        return None
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, _ = frame.shape
    image = QImage(frame.data, width, height, frame.strides[0], QImage.Format_RGB888)
    return image.copy()


def _load_with_qimage_reader(path: Path, target_size: int | None) -> QImage | None:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    if target_size is not None:
        original_size = reader.size()
        if original_size.isValid():
            scaled_size = original_size.scaled(target_size, target_size, Qt.KeepAspectRatio)
            reader.setScaledSize(scaled_size)
    image = reader.read()
    return image if not image.isNull() else None


def build_placeholder_image(label: str, size: int, video: bool = False) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor("#23262b"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#4f5b66"), 1))
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 8, 8)
    painter.setPen(QColor("#d9dde3"))
    font = QFont("Segoe UI", max(9, size // 8))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignCenter, label.replace(".", "").upper())
    if video:
        _draw_video_badge(painter, size)
    painter.end()
    return image


def build_placeholder(label: str, size: int, video: bool = False) -> QPixmap:
    return QPixmap.fromImage(build_placeholder_image(label, size, video))


def _draw_video_badge(painter: QPainter, size: int) -> None:
    badge_width = max(40, size // 2)
    painter.fillRect(size - badge_width - 6, size - 28, badge_width, 22, QColor(0, 0, 0, 170))
    painter.setPen(QColor("#f5f7fa"))
    painter.drawText(size - badge_width - 6, size - 28, badge_width, 22, Qt.AlignCenter, "VIDEO")


def _draw_sequence_badge(painter: QPainter, size: int) -> None:
    badge_width = max(26, size // 3)
    painter.fillRect(6, size - 28, badge_width, 22, QColor(0, 0, 0, 170))
    painter.setPen(QColor("#f5f7fa"))
    painter.drawText(6, size - 28, badge_width, 22, Qt.AlignCenter, "SEQ")


def _memory_cache_key(source_path: Path, size: int) -> tuple[str, int, int, int] | None:
    try:
        stat = source_path.stat()
        return (str(source_path.resolve()), stat.st_mtime_ns, stat.st_size, size)
    except OSError:
        return None


def _memory_cache_lookup(key: tuple[str, int, int, int]) -> QImage | None:
    with _memory_cache_lock:
        image = _memory_image_cache.get(key)
        if image is None:
            return None
        _memory_image_cache.move_to_end(key)
        return image.copy()


def _remember_image(key: tuple[str, int, int, int], image: QImage) -> None:
    global _memory_cache_bytes
    with _memory_cache_lock:
        previous = _memory_image_cache.pop(key, None)
        if previous is not None:
            _memory_cache_bytes -= previous.sizeInBytes()
        stored = image.copy()
        _memory_image_cache[key] = stored
        _memory_cache_bytes += stored.sizeInBytes()
        while _memory_image_cache and _memory_cache_bytes > _memory_cache_byte_limit:
            _, removed = _memory_image_cache.popitem(last=False)
            _memory_cache_bytes -= removed.sizeInBytes()


def _manifest_cache_path(source_path: Path, size: int) -> Path | None:
    library_root = find_library_cache_root(source_path)
    if library_root is None:
        return None
    try:
        relative_path = str(source_path.resolve().relative_to(library_root.resolve())).replace("\\", "/")
        stat = source_path.stat()
    except (OSError, ValueError):
        return None

    manifest = _load_manifest(library_root)
    entry = manifest.get("entries", {}).get(relative_path)
    if not isinstance(entry, dict):
        return None
    if entry.get("mtime_ns") != stat.st_mtime_ns or entry.get("size") != stat.st_size:
        return None

    thumbs = entry.get("thumbs", {})
    if not isinstance(thumbs, dict):
        return None
    relative_thumb = thumbs.get(str(size))
    if not isinstance(relative_thumb, str) or not relative_thumb:
        return None
    candidate = library_root / relative_thumb
    return candidate


def _load_manifest(root: Path) -> dict:
    with _manifest_cache_lock:
        manifest = _manifest_cache.get(root)
        if manifest is None:
            manifest = load_library_manifest(root)
            _manifest_cache[root] = manifest
        return manifest


def _store_manifest(root: Path, manifest: dict) -> None:
    with _manifest_cache_lock:
        _manifest_cache[root] = manifest
        save_library_manifest(root, manifest)
