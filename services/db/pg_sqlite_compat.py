"""Read-only PostgreSQL compatibility shim for legacy SQLite-style readers.

Converts ``?`` placeholders to ``%s`` and exposes integer indexing on rows so
existing ContextExpander / GraphTraverser SQL can run against PG unchanged.
"""

from __future__ import annotations

from typing import Any, Iterable


class _Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, rows):
        self._rows = [_Row(row) for row in rows]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class PGReadCompat:
    def __init__(self):
        from services.db.pg_pool import pg_connection

        self._pg = pg_connection()

    def execute(self, sql: str, params: Iterable[Any] = ()):
        return _Cursor(self._pg.execute(sql.replace("?", "%s"), tuple(params)).fetchall())

    def close(self) -> None:
        self._pg.close()
