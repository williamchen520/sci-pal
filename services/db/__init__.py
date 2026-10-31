"""Database adapter package (P1)."""

from .adapter import (
    DBAdapter,
    DBAdapterError,
    DBConfig,
    PostgresAdapter,
    SQLiteAdapter,
    create_adapter,
)

__all__ = [
    "DBAdapter",
    "DBAdapterError",
    "DBConfig",
    "PostgresAdapter",
    "SQLiteAdapter",
    "create_adapter",
]
