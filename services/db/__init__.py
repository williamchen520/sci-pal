"""Database adapter and ETL package (P1/P2)."""

from .adapter import (
    DBAdapter,
    DBAdapterError,
    DBConfig,
    PostgresAdapter,
    SQLiteAdapter,
    create_adapter,
)
from .etl import (
    DryRunWriter,
    ETLError,
    ETLReport,
    InMemoryWriter,
    LIVE_DB,
    PostgresCopyWriter,
    assert_snapshot,
    dry_run,
    run_etl,
)
from .shadow_read import FtsDiff, ShadowReader, TableDiff, write_report
from .dual_write import DEFAULT_TABLES, install, outbox_stats, replay
from .read_router import ReadResult, ReadRouter

__all__ = [
    "DBAdapter",
    "DBAdapterError",
    "DBConfig",
    "DEFAULT_TABLES",
    "DryRunWriter",
    "ETLError",
    "ETLReport",
    "InMemoryWriter",
    "FtsDiff",
    "LIVE_DB",
    "PostgresAdapter",
    "ReadResult",
    "ReadRouter",
    "PostgresCopyWriter",
    "SQLiteAdapter",
    "ShadowReader",
    "TableDiff",
    "assert_snapshot",
    "create_adapter",
    "dry_run",
    "install",
    "outbox_stats",
    "replay",
    "run_etl",
    "write_report",
]
