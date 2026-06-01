from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.sequence_detector import build_media_items
from app.tag_store import TagStore
from app.texture_sets import ROLE_SORT_ORDER, detect_role, texture_set_for_item
from app.utils import is_supported_media


class TagCsvExportWorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(str, int, int)
    error = Signal(str)


class TagCsvExportWorker(QRunnable):
    def __init__(self, roots: list[Path], tag_name: str, output_path: Path) -> None:
        super().__init__()
        self.roots = roots
        self.tag_name = tag_name
        self.output_path = output_path
        self.signals = TagCsvExportWorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            rows, skipped = self._collect_rows()
            if self._cancelled:
                return
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self._fieldnames())
                writer.writeheader()
                writer.writerows(rows)
            self.signals.finished.emit(str(self.output_path), len(rows), skipped)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))

    def _collect_rows(self) -> tuple[list[dict[str, str]], int]:
        folder_cache: dict[Path, list] = {}
        exported_keys: set[tuple[str, str]] = set()
        rows: list[dict[str, str]] = []
        skipped = 0
        processed = 0

        all_entries: list[tuple[Path, str, str, str]] = []
        for root in self.roots:
            entries = TagStore(root).tagged_entries(self.tag_name)
            for relative_path, scope, set_key in entries:
                all_entries.append((root, relative_path, scope, set_key))

        total = len(all_entries)
        for root, relative_path, scope, set_key in all_entries:
            if self._cancelled:
                return rows, skipped

            processed += 1
            if processed == 1 or processed % 25 == 0:
                self.signals.progress.emit(f"Exporting tag CSV... {processed}/{total}")

            absolute_path = root / Path(relative_path)
            if not absolute_path.exists():
                skipped += 1
                continue

            folder_items = folder_cache.get(absolute_path.parent)
            if folder_items is None:
                folder_items = self._folder_items_for(absolute_path.parent)
                folder_cache[absolute_path.parent] = folder_items
            if not folder_items:
                skipped += 1
                continue

            seed_item = self._find_seed_item(folder_items, absolute_path)
            if seed_item is None:
                skipped += 1
                continue

            texture_set = texture_set_for_item(seed_item, folder_items)
            export_key = (str(seed_item.folder.resolve()).lower(), texture_set.title.lower())
            if export_key in exported_keys:
                continue
            exported_keys.add(export_key)
            rows.append(self._row_for(texture_set, root, scope, set_key))

        rows.sort(key=lambda row: (row["library_root"].lower(), row["material_name"].lower()))
        return rows, skipped

    def _folder_items_for(self, folder: Path) -> list:
        paths = [path for path in folder.iterdir() if path.is_file() and is_supported_media(path)]
        if not paths:
            return []
        return build_media_items(paths, group_sequences=True)

    def _find_seed_item(self, items: list, absolute_path: Path):
        resolved_target = absolute_path.resolve()
        for item in items:
            try:
                if item.preview_path.resolve() == resolved_target:
                    return item
            except OSError:
                if item.preview_path == absolute_path:
                    return item
        return None

    def _row_for(self, texture_set, root: Path, scope: str, set_key: str) -> dict[str, str]:
        role_columns = {role: "" for role in ROLE_SORT_ORDER}
        uncategorized: list[str] = []
        all_paths: list[str] = []

        for item in texture_set.items:
            item_path = str(item.preview_path.resolve())
            all_paths.append(item_path)
            role = detect_role(item)
            if role is None:
                uncategorized.append(item_path)
                continue
            existing = role_columns.get(role, "")
            role_columns[role] = f"{existing}; {item_path}".strip("; ").strip()

        preview_path = ""
        try:
            preview_path = str(texture_set.seed.preview_path.resolve())
        except OSError:
            preview_path = str(texture_set.seed.preview_path)

        row = {
            "tag": self.tag_name,
            "library_root": str(root.resolve()),
            "material_name": texture_set.title,
            "folder": str(texture_set.seed.folder.resolve()),
            "tag_scope": scope,
            "tag_set_key": set_key,
            "seed_file": texture_set.seed.display_name,
            "preview_path": preview_path,
            "texture_count": str(len(texture_set.items)),
            "all_textures": "; ".join(all_paths),
            "uncategorized": "; ".join(uncategorized),
        }
        row.update(role_columns)
        return row

    def _fieldnames(self) -> list[str]:
        return [
            "tag",
            "library_root",
            "material_name",
            "folder",
            "tag_scope",
            "tag_set_key",
            "seed_file",
            "preview_path",
            "texture_count",
            *ROLE_SORT_ORDER,
            "uncategorized",
            "all_textures",
        ]
