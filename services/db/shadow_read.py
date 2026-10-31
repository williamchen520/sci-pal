"""P3 shadow read: compare SQLite snapshot with PostgreSQL.

Read-only. This module does not switch the production read path; it produces a
difference report for human review.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.db.etl import quote_ident, assert_snapshot


@dataclass
class TableDiff:
    table: str
    sqlite_rows: int = 0
    postgres_rows: int = 0
    compared: int = 0
    common_keys: int = 0
    missing_in_pg: int = 0
    extra_in_pg: int = 0
    field_diffs: int = 0
    samples: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"


@dataclass
class FtsDiff:
    query: str
    limit: int
    sqlite_top: List[str]
    postgres_top: List[str]
    common: int
    sqlite_only: int
    postgres_only: int
    jaccard: float
    sqlite_matches: int = 0
    postgres_matches: int = 0
    match_jaccard: float = 0.0
    sqlite_top_in_pg: int = 0
    postgres_top_in_sqlite: int = 0
    status: str = "ok"


class ShadowReader:
    def __init__(
        self,
        sqlite_path: str | Path,
        pg_conn: Any,
        *,
        pg_placeholder: str = "%s",
        sample_limit: int = 5,
    ):
        self.sqlite_path = assert_snapshot(sqlite_path)
        self.pg = pg_conn
        self.pg_placeholder = pg_placeholder
        self.sample_limit = sample_limit

    def _sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _columns(self, conn: sqlite3.Connection, table: str) -> List[str]:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})")]

    @staticmethod
    def _row_tuple(row: Any) -> tuple:
        if isinstance(row, dict):
            return tuple(row.values())
        return tuple(row)

    def compare_table(
        self,
        table: str,
        key: str,
        *,
        limit: int = 200,
        columns: Optional[Sequence[str]] = None,
    ) -> TableDiff:
        sqlite_conn = self._sqlite()
        try:
            if columns is None:
                columns = self._columns(sqlite_conn, table)
            if key not in columns:
                raise ValueError(f"key {key!r} not in {table}")
            cols = ", ".join(quote_ident(col) for col in columns)
            key_col = quote_ident(key)
            sqlite_count = sqlite_conn.execute(
                f"SELECT COUNT(*) FROM {quote_ident(table)}"
            ).fetchone()[0]
            pg_count = self._pg_count(table)
            diff = TableDiff(table=table, sqlite_rows=sqlite_count, postgres_rows=pg_count)

            # Compare the full key set, not LIMIT slices: text collation differs.
            sqlite_keys = {
                self._row_tuple(row)[0]
                for row in sqlite_conn.execute(f"SELECT {key_col} FROM {quote_ident(table)}")
            }
            pg_keys = {
                self._row_tuple(row)[0]
                for row in self.pg.execute(f"SELECT {key_col} FROM {quote_ident(table)}")
            }
            common = sqlite_keys & pg_keys
            diff.common_keys = len(common)
            diff.missing_in_pg = len(sqlite_keys - pg_keys)
            diff.extra_in_pg = len(pg_keys - sqlite_keys)

            sample_keys = sorted(common, key=lambda value: str(value))[:limit]
            if sample_keys:
                placeholders = ", ".join(["?"] * len(sample_keys))
                sqlite_rows = sqlite_conn.execute(
                    f"SELECT {cols} FROM {quote_ident(table)} "
                    f"WHERE {key_col} IN ({placeholders}) ORDER BY {key_col}",
                    tuple(sample_keys),
                ).fetchall()
                pg_placeholders = ", ".join([self.pg_placeholder] * len(sample_keys))
                pg_rows = self.pg.execute(
                    f"SELECT {cols} FROM {quote_ident(table)} "
                    f"WHERE {key_col} IN ({pg_placeholders}) ORDER BY {key_col}",
                    tuple(sample_keys),
                ).fetchall()
            else:
                sqlite_rows, pg_rows = [], []
            sqlite_map = {self._row_tuple(row)[0]: self._row_tuple(row) for row in sqlite_rows}
            pg_map = {self._row_tuple(row)[0]: self._row_tuple(row) for row in pg_rows}
            diff.compared = len(set(sqlite_map) & set(pg_map))
            for key_value in sorted(sqlite_map, key=lambda value: str(value)):
                if key_value not in pg_map:
                    continue
                left = sqlite_map[key_value]
                right = pg_map[key_value]
                if left != right:
                    diff.field_diffs += 1
                    if len(diff.samples) < self.sample_limit:
                        diff.samples.append(
                            {
                                "key": str(key_value),
                                "fields": [
                                    columns[i]
                                    for i, (a, b) in enumerate(zip(left, right))
                                    if a != b
                                ],
                            }
                        )
            if (
                diff.sqlite_rows != diff.postgres_rows
                or diff.missing_in_pg
                or diff.extra_in_pg
                or diff.field_diffs
            ):
                diff.status = "diff"
            return diff
        finally:
            sqlite_conn.close()

    def _pg_count(self, table: str) -> int:
        row = self.pg.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()
        if isinstance(row, dict):
            return int(next(iter(row.values())))
        return int(row[0])

    def compare_fts(self, query: str, *, limit: int = 10) -> FtsDiff:
        sqlite_conn = self._sqlite()
        try:
            sqlite_top = [
                row[0]
                for row in sqlite_conn.execute(
                    """
                    SELECT para_id FROM paragraphs_fts
                    WHERE paragraphs_fts MATCH ?
                    ORDER BY bm25(paragraphs_fts)
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
            ]
            sqlite_matches = {
                row[0]
                for row in sqlite_conn.execute(
                    "SELECT para_id FROM paragraphs_fts WHERE paragraphs_fts MATCH ?",
                    (query,),
                )
            }
        finally:
            sqlite_conn.close()

        pg_rows = self.pg.execute(
            """
            SELECT para_id FROM paragraphs
            WHERE search_vector @@ websearch_to_tsquery('english', %s)
            ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) DESC
            LIMIT %s
            """
            % (self.pg_placeholder, self.pg_placeholder, self.pg_placeholder),
            (query, query, limit),
        ).fetchall()
        pg_top = [self._row_tuple(row)[0] for row in pg_rows]
        pg_matches = {
            self._row_tuple(row)[0]
            for row in self.pg.execute(
                "SELECT para_id FROM paragraphs "
                "WHERE search_vector @@ websearch_to_tsquery('english', %s)"
                % self.pg_placeholder,
                (query,),
            ).fetchall()
        }

        sqlite_top_set = set(sqlite_top)
        pg_top_set = set(pg_top)
        match_union = len(sqlite_matches | pg_matches)
        match_common = len(sqlite_matches & pg_matches)
        top_union = len(sqlite_top_set | pg_top_set)
        top_common = len(sqlite_top_set & pg_top_set)
        if sqlite_matches == pg_matches and sqlite_top_set == pg_top_set:
            status = "ok"
        elif sqlite_matches == pg_matches:
            status = "ranking_diff"
        else:
            status = "diff"
        return FtsDiff(
            query=query,
            limit=limit,
            sqlite_top=sqlite_top,
            postgres_top=pg_top,
            common=top_common,
            sqlite_only=len(sqlite_top_set - pg_top_set),
            postgres_only=len(pg_top_set - sqlite_top_set),
            jaccard=(top_common / top_union) if top_union else 1.0,
            sqlite_matches=len(sqlite_matches),
            postgres_matches=len(pg_matches),
            match_jaccard=(match_common / match_union) if match_union else 1.0,
            sqlite_top_in_pg=len(sqlite_top_set & pg_matches),
            postgres_top_in_sqlite=len(pg_top_set & sqlite_matches),
            status=status,
        )

    def run(
        self,
        tables: Sequence[tuple[str, str]],
        *,
        limit: int = 200,
        fts_queries: Sequence[str] = (),
        fts_limit: int = 10,
    ) -> Dict[str, Any]:
        report = {
            "source": str(self.sqlite_path),
            "limit": limit,
            "tables": [],
            "fts": [],
            "status": "ok",
        }
        for table, key in tables:
            item = self.compare_table(table, key, limit=limit)
            report["tables"].append(asdict(item))
        for query in fts_queries:
            item = self.compare_fts(query, limit=fts_limit)
            report["fts"].append(asdict(item))
        if any(item["status"] != "ok" for item in report["tables"]) or any(
            item["status"] != "ok" for item in report["fts"]
        ):
            report["status"] = "diff"
        return report


def write_report(report: Dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
