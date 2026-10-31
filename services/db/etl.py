"""Read-only SQLite -> PostgreSQL ETL core (P2).

The source must be a snapshot, never ``data/research.db``. The writer abstraction
lets tests dry-run without a PostgreSQL server; the real writer uses COPY.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LIVE_DB = PROJECT_ROOT / "data" / "research.db"


class ETLError(RuntimeError):
    """Raised when an ETL safety or execution rule is violated."""


def assert_snapshot(source: str | Path) -> Path:
    """Reject the live database; ETL may only read a snapshot."""
    path = Path(source).resolve()
    if path == LIVE_DB.resolve():
        raise ETLError(
            "refusing to ETL the live data/research.db; use a snapshot from backups/"
        )
    if not path.exists():
        raise ETLError(f"source snapshot not found: {path}")
    return path


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def list_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})")]


def table_checksum(
    conn: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
) -> str:
    digest = hashlib.sha256()
    select = ", ".join(quote_ident(col) for col in columns)
    for row in conn.execute(f"SELECT {select} FROM {quote_ident(table)}"):
        digest.update(repr(tuple(row)).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class TargetWriter(Protocol):
    def copy_table(
        self,
        table: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[Any]],
    ) -> int:
        ...


class DryRunWriter:
    """Count rows without writing anywhere."""

    def copy_table(self, table, columns, rows) -> int:
        count = 0
        for _ in rows:
            count += 1
        return count


class InMemoryWriter:
    """Test writer that keeps a small sample and counts rows."""

    def __init__(self, sample_limit: int = 3):
        self.sample_limit = sample_limit
        self.tables: Dict[str, List[Sequence[Any]]] = {}
        self.counts: Dict[str, int] = {}

    def copy_table(self, table, columns, rows) -> int:
        count = 0
        sample: List[Sequence[Any]] = []
        for row in rows:
            if len(sample) < self.sample_limit:
                sample.append(tuple(row))
            count += 1
        self.tables[table] = sample
        self.counts[table] = count
        return count


class PostgresCopyWriter:
    """COPY rows into PostgreSQL using psycopg3."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def copy_table(self, table, columns, rows) -> int:
        try:
            import psycopg
        except ImportError as exc:
            raise ETLError(
                "psycopg is required for ETL execution; install psycopg[binary]"
            ) from exc
        cols = ", ".join(quote_ident(col) for col in columns)
        sql = f"COPY {quote_ident(table)} ({cols}) FROM STDIN"
        count = 0
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                with cur.copy(sql) as copy:
                    for row in rows:
                        copy.write_row(row)
                        count += 1
        return count


@dataclass
class TableReport:
    table: str
    rows: int
    checksum: Optional[str] = None
    status: str = "ok"
    error: Optional[str] = None


@dataclass
class ETLReport:
    source: str
    tables: List[TableReport] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "tables": [vars(item) for item in self.tables],
            "total_rows": sum(item.rows for item in self.tables),
        }


def _selected_tables(conn: sqlite3.Connection, tables: Optional[Sequence[str]]) -> List[str]:
    available = set(list_tables(conn))
    if tables is None:
        return sorted(available)
    missing = [name for name in tables if name not in available]
    if missing:
        raise ETLError(f"unknown tables: {', '.join(missing)}")
    return list(tables)


def dry_run(
    source: str | Path,
    *,
    tables: Optional[Sequence[str]] = None,
    checksum: bool = False,
) -> ETLReport:
    path = assert_snapshot(source)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    report = ETLReport(source=str(path))
    try:
        for table in _selected_tables(conn, tables):
            columns = table_columns(conn, table)
            count = conn.execute(
                f"SELECT COUNT(*) FROM {quote_ident(table)}"
            ).fetchone()[0]
            digest = table_checksum(conn, table, columns) if checksum else None
            report.tables.append(TableReport(table, count, digest))
    finally:
        conn.close()
    return report


def run_etl(
    source: str | Path,
    writer: TargetWriter,
    *,
    tables: Optional[Sequence[str]] = None,
    checksum: bool = False,
) -> ETLReport:
    path = assert_snapshot(source)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    report = ETLReport(source=str(path))
    try:
        for table in _selected_tables(conn, tables):
            columns = table_columns(conn, table)
            digest = table_checksum(conn, table, columns) if checksum else None
            select = ", ".join(quote_ident(col) for col in columns)
            rows = conn.execute(
                f"SELECT {select} FROM {quote_ident(table)}"
            )
            try:
                count = writer.copy_table(table, columns, rows)
                report.tables.append(TableReport(table, count, digest))
            except Exception as exc:  # noqa: BLE001 - report per-table failure
                report.tables.append(
                    TableReport(table, 0, digest, status="failed", error=str(exc))
                )
    finally:
        conn.close()
    return report
