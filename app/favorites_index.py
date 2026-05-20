from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.models import MediaItem, MediaKind, SequenceInfo
from app.sequence_detector import build_media_items
from app.utils import app_data_dir, is_cache_folder, is_supported_media


class FavoritesIndexWorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(list, int)
    error = Signal(str)


class FavoritesIndexWorker(QRunnable):
    def __init__(self, roots: list[Path], store: "FavoritesIndexStore") -> None:
        super().__init__()
        self.roots = roots
        self.store = store
        self.signals = FavoritesIndexWorkerSignals()

    def run(self) -> None:
        try:
            all_items: list[MediaItem] = []
            indexed_roots = 0
            for root in self.roots:
                if not root.exists():
                    continue
                self.signals.progress.emit(f"Loading favorites index: {root}")
                if self.store.has_index(root):
                    items = self.store.load_index(root)
                else:
                    self.signals.progress.emit(f"Building favorites index: {root}")
                    items = self.store.build_index(root, self.signals.progress.emit)
                    self.store.save_index(root, items)
                all_items.extend(items)
                indexed_roots += 1

            all_items.sort(key=lambda item: (str(item.folder).lower(), item.display_name.lower()))
            self.signals.finished.emit(all_items, indexed_roots)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))


class FavoritesIndexStore:
    def __init__(self) -> None:
        self.root = app_data_dir() / "favorites_index"
        self.root.mkdir(parents=True, exist_ok=True)

    def has_index(self, root: Path) -> bool:
        return self._index_path(root).exists()

    def load_index(self, root: Path) -> list[MediaItem]:
        index_path = self._index_path(root)
        if not index_path.exists():
            return []
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []

        items_payload = payload.get("items", [])
        if not isinstance(items_payload, list):
            return []

        items: list[MediaItem] = []
        for item_payload in items_payload:
            item = self._deserialize_item(item_payload)
            if item is None:
                continue
            items.append(item)
        return items

    def save_index(self, root: Path, items: list[MediaItem]) -> None:
        payload = {
            "root": str(root),
            "items": [self._serialize_item(item) for item in items],
        }
        index_path = self._index_path(root)
        index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def build_index(self, root: Path, progress_callback=None) -> list[MediaItem]:
        items: list[MediaItem] = []
        seen = 0
        found = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not is_cache_folder(Path(name))]
            directory = Path(dirpath)
            paths: list[Path] = []
            for filename in filenames:
                path = directory / filename
                seen += 1
                if progress_callback is not None and seen % 500 == 0:
                    progress_callback(f"Indexing favorites... {seen} files checked, {found} items found")
                if is_supported_media(path):
                    paths.append(path)
            if not paths:
                continue
            directory_items = build_media_items(paths)
            items.extend(directory_items)
            found += len(directory_items)

        items.sort(key=lambda item: (str(item.folder).lower(), item.display_name.lower()))
        return items

    def _index_path(self, root: Path) -> Path:
        digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def _serialize_item(self, item: MediaItem) -> dict:
        payload = {
            "display_name": item.display_name,
            "path": str(item.path),
            "kind": item.kind.value,
            "extension": item.extension,
            "folder": str(item.folder),
            "search_text": item.search_text,
            "metadata": item.metadata,
        }
        if item.sequence is not None:
            payload["sequence"] = {
                "pattern_name": item.sequence.pattern_name,
                "frame_paths": [str(path) for path in item.sequence.frame_paths],
                "frame_numbers": item.sequence.frame_numbers,
                "padding": item.sequence.padding,
            }
        return payload

    def _deserialize_item(self, payload: dict) -> MediaItem | None:
        if not isinstance(payload, dict):
            return None
        try:
            path = Path(payload["path"])
            folder = Path(payload["folder"])
            kind = MediaKind(payload["kind"])
            display_name = str(payload["display_name"])
            extension = str(payload["extension"])
            search_text = str(payload["search_text"])
        except (KeyError, TypeError, ValueError):
            return None

        sequence_payload = payload.get("sequence")
        sequence = None
        if isinstance(sequence_payload, dict):
            try:
                frame_paths = [Path(frame_path) for frame_path in sequence_payload["frame_paths"]]
                frame_numbers = [int(value) for value in sequence_payload["frame_numbers"]]
                sequence = SequenceInfo(
                    pattern_name=str(sequence_payload["pattern_name"]),
                    frame_paths=frame_paths,
                    frame_numbers=frame_numbers,
                    padding=int(sequence_payload["padding"]),
                )
            except (KeyError, TypeError, ValueError):
                sequence = None

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        return MediaItem(
            display_name=display_name,
            path=path,
            kind=kind,
            extension=extension,
            folder=folder,
            search_text=search_text,
            sequence=sequence,
            metadata=metadata,
        )
