from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.models import MediaItem
from app.utils import ensure_library_cache, library_cache_root

TAGS_DB_NAME = "tags.sqlite"


def normalize_tag_name(tag_name: str) -> str:
    return " ".join(tag_name.strip().split())


def tag_database_path(root: Path) -> Path:
    return library_cache_root(root.resolve()) / TAGS_DB_NAME


def tag_database_exists(root: Path) -> bool:
    return tag_database_path(root).exists()


class TagStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        ensure_library_cache(self.root)
        self.path = tag_database_path(self.root)
        self._ensure_schema()

    def list_tags(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("select name from tags order by lower(name)").fetchall()
        return [str(row[0]) for row in rows]

    def create_tag(self, tag_name: str) -> bool:
        tag_name = normalize_tag_name(tag_name)
        if not tag_name:
            return False
        with self._connect() as connection:
            self._tag_id(connection, tag_name)
        return True

    def delete_tag(self, tag_name: str) -> int:
        tag_name = normalize_tag_name(tag_name)
        if not tag_name:
            return 0
        with self._connect() as connection:
            row = connection.execute("select id from tags where lower(name) = lower(?)", (tag_name,)).fetchone()
            if row is None:
                return 0
            tag_id = int(row[0])
            connection.execute("delete from tagged_files where tag_id = ?", (tag_id,))
            connection.execute("delete from tags where id = ?", (tag_id,))
            return connection.total_changes

    def add_items(self, tag_name: str, items: list[MediaItem], scope: str = "file", set_key: str = "") -> int:
        tag_name = normalize_tag_name(tag_name)
        if not tag_name:
            return 0
        relative_paths = self._relative_paths_for_items(items)
        if not relative_paths:
            return 0

        now = int(time.time())
        with self._connect() as connection:
            tag_id = self._tag_id(connection, tag_name)
            connection.executemany(
                """
                insert or replace into tagged_files(tag_id, relative_path, scope, set_key, added_at)
                values (?, ?, ?, ?, ?)
                """,
                [(tag_id, relative_path, scope, set_key, now) for relative_path in relative_paths],
            )
        return len(relative_paths)

    def remove_items(self, tag_name: str, items: list[MediaItem]) -> int:
        tag_name = normalize_tag_name(tag_name)
        if not tag_name:
            return 0
        relative_paths = self._relative_paths_for_items(items)
        if not relative_paths:
            return 0

        with self._connect() as connection:
            row = connection.execute("select id from tags where lower(name) = lower(?)", (tag_name,)).fetchone()
            if row is None:
                return 0
            tag_id = int(row[0])
            connection.executemany(
                "delete from tagged_files where tag_id = ? and relative_path = ?",
                [(tag_id, relative_path) for relative_path in relative_paths],
            )
            deleted = connection.total_changes
            self._delete_empty_tags(connection)
        return deleted

    def tags_for_items(self, items: list[MediaItem]) -> list[str]:
        relative_paths = self._relative_paths_for_items(items)
        if not relative_paths:
            return []
        placeholders = ",".join("?" for _ in relative_paths)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                select distinct tags.name
                from tags
                join tagged_files on tagged_files.tag_id = tags.id
                where tagged_files.relative_path in ({placeholders})
                order by lower(tags.name)
                """,
                relative_paths,
            ).fetchall()
        return [str(row[0]) for row in rows]

    def tagged_paths(self, tag_name: str) -> set[str]:
        tag_name = normalize_tag_name(tag_name)
        if not tag_name:
            return set()
        with self._connect() as connection:
            rows = connection.execute(
                """
                select tagged_files.relative_path
                from tagged_files
                join tags on tags.id = tagged_files.tag_id
                where lower(tags.name) = lower(?)
                """,
                (tag_name,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def relative_path_for_item(self, item: MediaItem) -> str | None:
        try:
            return str(item.preview_path.resolve().relative_to(self.root)).replace("\\", "/")
        except (OSError, ValueError):
            return None

    def _relative_paths_for_items(self, items: list[MediaItem]) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for item in items:
            relative_path = self.relative_path_for_item(item)
            if relative_path is None or relative_path in seen:
                continue
            seen.add(relative_path)
            paths.append(relative_path)
        return paths

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists tags (
                    id integer primary key,
                    name text not null unique
                )
                """
            )
            connection.execute(
                """
                create table if not exists tagged_files (
                    tag_id integer not null,
                    relative_path text not null,
                    scope text not null default 'file',
                    set_key text not null default '',
                    added_at integer not null,
                    primary key (tag_id, relative_path),
                    foreign key(tag_id) references tags(id) on delete cascade
                )
                """
            )
            self._merge_duplicate_tags(connection)
            connection.execute(
                "create index if not exists idx_tagged_files_relative_path on tagged_files(relative_path)"
            )
            connection.execute("create unique index if not exists idx_tags_name_nocase on tags(lower(name))")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("pragma foreign_keys = on")
        return connection

    def _tag_id(self, connection: sqlite3.Connection, tag_name: str) -> int:
        tag_name = normalize_tag_name(tag_name)
        connection.execute("insert or ignore into tags(name) values (?)", (tag_name,))
        row = connection.execute("select id from tags where lower(name) = lower(?)", (tag_name,)).fetchone()
        if row is None:
            raise RuntimeError("Could not create tag.")
        return int(row[0])

    def _delete_empty_tags(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            delete from tags
            where not exists (
                select 1 from tagged_files where tagged_files.tag_id = tags.id
            )
            """
        )

    def _merge_duplicate_tags(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("select id, name from tags order by lower(name), id").fetchall()
        canonical_by_key: dict[str, tuple[int, str]] = {}
        duplicate_ids: list[int] = []

        for row in rows:
            tag_id = int(row[0])
            tag_name = normalize_tag_name(str(row[1]))
            if not tag_name:
                duplicate_ids.append(tag_id)
                continue

            key = tag_name.lower()
            canonical = canonical_by_key.get(key)
            if canonical is None:
                canonical_by_key[key] = (tag_id, tag_name)
                if tag_name != str(row[1]):
                    connection.execute("update tags set name = ? where id = ?", (tag_name, tag_id))
                continue

            canonical_id, _canonical_name = canonical
            connection.execute(
                """
                insert or replace into tagged_files(tag_id, relative_path, scope, set_key, added_at)
                select ?, relative_path, scope, set_key, added_at
                from tagged_files
                where tag_id = ?
                """,
                (canonical_id, tag_id),
            )
            connection.execute("delete from tagged_files where tag_id = ?", (tag_id,))
            duplicate_ids.append(tag_id)

        if duplicate_ids:
            connection.executemany("delete from tags where id = ?", [(tag_id,) for tag_id in duplicate_ids])
