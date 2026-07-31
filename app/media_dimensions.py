from __future__ import annotations

import atexit
import os
from pathlib import Path
import sqlite3
import threading

from PySide6.QtGui import QImageReader

from app.utils import app_data_dir

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


_dimension_cache_lock = threading.RLock()
_dimension_cache_connection: sqlite3.Connection | None = None
_dimension_cache_pending_writes = 0
_DIMENSION_CACHE_COMMIT_BATCH = 128


def media_dimensions(path: Path, metadata: dict | None = None) -> tuple[int, int] | None:
    cached = _cached_dimensions(metadata)
    if cached is not None:
        return cached
    if isinstance(metadata, dict) and metadata.get("dimensions_error") == "1":
        return None

    signature = _file_signature(path)
    if signature is not None:
        disk_cached = _dimension_cache_lookup(signature)
        if disk_cached is not None:
            dimensions, failed = disk_cached
            if isinstance(metadata, dict):
                if failed:
                    metadata["dimensions_error"] = "1"
                elif dimensions is not None:
                    metadata["dimensions"] = f"{dimensions[0]}x{dimensions[1]}"
                    metadata.pop("dimensions_error", None)
            return dimensions

    dimensions = _probe_dimensions(path)
    if signature is not None:
        _dimension_cache_store(signature, dimensions)
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


def _file_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    normalized_path = os.path.normcase(os.path.abspath(os.fspath(path)))
    return (normalized_path, stat.st_mtime_ns, stat.st_size)


def _dimension_cache() -> sqlite3.Connection | None:
    global _dimension_cache_connection
    with _dimension_cache_lock:
        if _dimension_cache_connection is not None:
            return _dimension_cache_connection
        try:
            database_path = app_data_dir() / "media_dimensions.sqlite3"
            connection = sqlite3.connect(database_path, check_same_thread=False, timeout=5.0)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dimensions (
                    path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL,
                    file_size INTEGER NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    failed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            _dimension_cache_connection = connection
        except (OSError, sqlite3.Error):
            _dimension_cache_connection = None
        return _dimension_cache_connection


def _dimension_cache_lookup(
    signature: tuple[str, int, int],
) -> tuple[tuple[int, int] | None, bool] | None:
    connection = _dimension_cache()
    if connection is None:
        return None
    path_key, mtime_ns, file_size = signature
    with _dimension_cache_lock:
        try:
            row = connection.execute(
                "SELECT mtime_ns, file_size, width, height, failed FROM dimensions WHERE path = ?",
                (path_key,),
            ).fetchone()
        except sqlite3.Error:
            return None
    if row is None or row[0] != mtime_ns or row[1] != file_size:
        return None
    failed = bool(row[4])
    if failed or row[2] is None or row[3] is None:
        return (None, failed)
    return ((int(row[2]), int(row[3])), False)


def _dimension_cache_store(
    signature: tuple[str, int, int],
    dimensions: tuple[int, int] | None,
) -> None:
    global _dimension_cache_pending_writes
    connection = _dimension_cache()
    if connection is None:
        return
    path_key, mtime_ns, file_size = signature
    width = dimensions[0] if dimensions is not None else None
    height = dimensions[1] if dimensions is not None else None
    with _dimension_cache_lock:
        try:
            connection.execute(
                """
                INSERT INTO dimensions(path, mtime_ns, file_size, width, height, failed)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    mtime_ns = excluded.mtime_ns,
                    file_size = excluded.file_size,
                    width = excluded.width,
                    height = excluded.height,
                    failed = excluded.failed
                """,
                (path_key, mtime_ns, file_size, width, height, int(dimensions is None)),
            )
            _dimension_cache_pending_writes += 1
            if _dimension_cache_pending_writes >= _DIMENSION_CACHE_COMMIT_BATCH:
                connection.commit()
                _dimension_cache_pending_writes = 0
        except sqlite3.Error:
            return


def _close_dimension_cache() -> None:
    global _dimension_cache_connection, _dimension_cache_pending_writes
    with _dimension_cache_lock:
        if _dimension_cache_connection is None:
            return
        try:
            _dimension_cache_connection.commit()
            _dimension_cache_connection.close()
        except sqlite3.Error:
            pass
        _dimension_cache_connection = None
        _dimension_cache_pending_writes = 0


atexit.register(_close_dimension_cache)
