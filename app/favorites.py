from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings


class FavoritesStore:
    def __init__(self) -> None:
        self.settings = QSettings("TextureBrowser", "TextureBrowser")

    def load(self) -> list[Path]:
        values = self.settings.value("favorites", [], list)
        paths = [Path(value) for value in values]
        return [path for path in paths if path.exists()]

    def save(self, favorites: list[Path]) -> None:
        unique = []
        seen = set()
        for path in favorites:
            resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        self.settings.setValue("favorites", unique)

    def load_favorites_search_enabled(self, favorites: list[Path]) -> list[Path]:
        if not self.settings.contains("favorites_search_enabled"):
            return list(favorites)
        values = self.settings.value("favorites_search_enabled", [], list)
        enabled = [Path(value) for value in values]
        valid = {path.resolve() for path in favorites if path.exists()}
        return [path for path in enabled if path.exists() and path.resolve() in valid]

    def save_favorites_search_enabled(self, favorites: list[Path]) -> None:
        unique = []
        seen = set()
        for path in favorites:
            resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        self.settings.setValue("favorites_search_enabled", unique)

    def load_last_root(self) -> Path | None:
        value = self.settings.value("last_root", "", str)
        if not value:
            return None
        path = Path(value)
        return path if path.exists() else None

    def save_last_root(self, path: Path) -> None:
        self.settings.setValue("last_root", str(path))

    def load_thumbnail_size(self) -> str:
        return self.settings.value("thumbnail_size", "Medium", str)

    def save_thumbnail_size(self, value: str) -> None:
        self.settings.setValue("thumbnail_size", value)

    def load_naming_convention(self) -> str:
        return self.settings.value("naming_convention", "", str)

    def save_naming_convention(self, value: str) -> None:
        self.settings.setValue("naming_convention", value)

    def load_sequence_grouping_enabled(self) -> bool:
        return self.settings.value("sequence_grouping_enabled", True, bool)

    def save_sequence_grouping_enabled(self, value: bool) -> None:
        self.settings.setValue("sequence_grouping_enabled", bool(value))

    def load_naming_presets(self) -> dict[str, str]:
        value = self.settings.value("naming_presets", "{}", str)
        try:
            presets = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(presets, dict):
            return {}
        cleaned: dict[str, str] = {}
        for name, convention in presets.items():
            if not isinstance(name, str) or not isinstance(convention, str):
                continue
            name = name.strip()
            if name:
                cleaned[name] = convention
        return dict(sorted(cleaned.items(), key=lambda item: item[0].lower()))

    def save_naming_presets(self, presets: dict[str, str]) -> None:
        cleaned = {
            name.strip(): convention
            for name, convention in presets.items()
            if name.strip()
        }
        self.settings.setValue("naming_presets", json.dumps(cleaned, sort_keys=True))
