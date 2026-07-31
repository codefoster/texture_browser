from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtGui import QImage

from app.favorites_index import FavoritesIndexStore
from app.godot_renderer import _material_arguments
import app.media_dimensions as dimensions_module
from app.models import MediaItem, MediaKind
from app.texture_sets import TextureSet
from app.thumbnailer import load_or_create_thumbnail


def media_item(path: Path, role_name: str | None = None) -> MediaItem:
    return MediaItem(
        display_name=path.name,
        path=path,
        kind=MediaKind.IMAGE,
        extension=path.suffix.lower(),
        folder=path.parent,
        search_text=path.name.lower(),
        metadata={"role": role_name} if role_name else {},
    )


class ThumbnailWorkerTests(unittest.TestCase):
    def test_thumbnail_generation_returns_qimage_from_worker_thread(self) -> None:
        with TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            source = root / "material_albedo.png"
            source_image = QImage(32, 16, QImage.Format_RGBA8888)
            source_image.fill(0xFF336699)
            self.assertTrue(source_image.save(str(source), "PNG"))
            output = root / "thumbnail.png"
            item = media_item(source)

            with (
                patch("app.thumbnailer._manifest_cache_path", return_value=None),
                patch("app.thumbnailer._cache_candidates", return_value=[]),
                patch("app.thumbnailer._preferred_cache_path", return_value=output),
                ThreadPoolExecutor(max_workers=1) as executor,
            ):
                thumbnail = executor.submit(load_or_create_thumbnail, item, 64).result(timeout=5)

            self.assertIsInstance(thumbnail, QImage)
            self.assertFalse(thumbnail.isNull())
            self.assertEqual((thumbnail.width(), thumbnail.height()), (64, 64))
            self.assertTrue(output.exists())


class FavoritesIndexTests(unittest.TestCase):
    def test_index_reuse_and_directory_change_invalidation(self) -> None:
        with TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "library"
            root.mkdir()
            source = root / "stone_albedo.png"
            source.write_bytes(b"not decoded during indexing")

            store = FavoritesIndexStore.__new__(FavoritesIndexStore)
            store.root = Path(temp_directory) / "indexes"
            store.root.mkdir()
            items = store.build_index(root)
            store.save_index(root, items)

            loaded = store.load_index(root)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded), 1)

            original_mtime = root.stat().st_mtime_ns
            changed = root / "stone_normal.png"
            changed.write_bytes(b"new file")
            os.utime(root, ns=(original_mtime + 1_000_000, original_mtime + 1_000_000))
            self.assertIsNone(store.load_index(root))


class DimensionCacheTests(unittest.TestCase):
    def test_dimension_result_is_reused_without_reopening_image(self) -> None:
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.execute(
            """
            CREATE TABLE dimensions (
                path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                failed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        previous_connection = dimensions_module._dimension_cache_connection
        previous_pending = dimensions_module._dimension_cache_pending_writes
        dimensions_module._dimension_cache_connection = connection
        dimensions_module._dimension_cache_pending_writes = 0
        try:
            with TemporaryDirectory() as temp_directory:
                source = Path(temp_directory) / "dimensions.png"
                image = QImage(40, 20, QImage.Format_RGBA8888)
                image.fill(0xFFFFFFFF)
                self.assertTrue(image.save(str(source), "PNG"))
                self.assertEqual(dimensions_module.media_dimensions(source), (40, 20))
                with patch("app.media_dimensions._probe_dimensions", side_effect=AssertionError("cache miss")):
                    self.assertEqual(dimensions_module.media_dimensions(source), (40, 20))
        finally:
            connection.close()
            dimensions_module._dimension_cache_connection = previous_connection
            dimensions_module._dimension_cache_pending_writes = previous_pending


class MaterialRendererArgumentTests(unittest.TestCase):
    def test_material_roles_become_renderer_arguments(self) -> None:
        root = Path("C:/materials/stone")
        albedo = media_item(root / "stone_albedo.png")
        normal = media_item(root / "stone_normal.png")
        roughness = media_item(root / "stone_roughness.png")
        texture_set = TextureSet(
            seed=albedo,
            items=[albedo, normal, roughness],
            identity_tokens=("stone",),
            roles={"basecolor": [albedo], "normal": [normal], "roughness": [roughness]},
        )

        arguments = _material_arguments(texture_set)

        self.assertIn("--basecolor", arguments)
        self.assertIn("--normal", arguments)
        self.assertIn("--roughness", arguments)
        self.assertNotIn("--use_packed", arguments)


if __name__ == "__main__":
    unittest.main()
