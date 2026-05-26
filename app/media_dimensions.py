from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImageReader

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import imageio.v3 as iio
except ImportError:  # pragma: no cover
    iio = None

try:
    from psd_tools import PSDImage
except ImportError:  # pragma: no cover
    PSDImage = None


def media_dimensions(path: Path, metadata: dict | None = None) -> tuple[int, int] | None:
    cached = _cached_dimensions(metadata)
    if cached is not None:
        return cached
    if isinstance(metadata, dict) and metadata.get("dimensions_error") == "1":
        return None

    dimensions = _probe_dimensions(path)
    if isinstance(metadata, dict):
        if dimensions is None:
            metadata["dimensions_error"] = "1"
        else:
            metadata["dimensions"] = f"{dimensions[0]}x{dimensions[1]}"
            metadata.pop("dimensions_error", None)
    return dimensions


def _cached_dimensions(metadata: dict | None) -> tuple[int, int] | None:
    if not isinstance(metadata, dict):
        return None
    cached = metadata.get("dimensions")
    if isinstance(cached, str) and "x" in cached:
        try:
            width_text, height_text = cached.split("x", 1)
            return (int(width_text), int(height_text))
        except ValueError:
            return None
    return None


def _probe_dimensions(path: Path) -> tuple[int, int] | None:
    ext = path.suffix.lower()

    if ext == ".psd" and PSDImage is not None:
        try:
            document = PSDImage.open(path)
            return (int(document.width), int(document.height))
        except Exception:
            pass

    if Image is not None:
        try:
            with Image.open(path) as image:
                return (int(image.width), int(image.height))
        except Exception:
            pass

    if iio is not None:
        try:
            props = iio.improps(path)
            shape = getattr(props, "shape", None)
            if shape is not None and len(shape) >= 2:
                return (int(shape[1]), int(shape[0]))
        except Exception:
            pass

    try:
        reader = QImageReader(str(path))
        size = reader.size()
        if size.isValid():
            return (size.width(), size.height())
    except Exception:
        pass
    return None
