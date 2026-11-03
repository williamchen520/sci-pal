#!/usr/bin/env python3
"""Shadow-compare SQLite FTS5 vs PostgreSQL FTS for paragraphs and summaries.

Read-only. Uses the same extracted terms on both sides; ranking differs by
design (SQLite bm25 vs PostgreSQL ts_rank/ts_rank_cd).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.db.pg_pool import close_pools, pg_connection  # noqa: E402
from services.search.fts_query_builder import _extract_keywords  # noqa: E402
from services.search.pg_fts import PGParagraphFTS, PGSummaryFTS  # noqa: E402


def _sqlite_ids(db: str, table: str, key: str, query: str, top_k: int) -> list[str]:
    terms = _extract_keywords(query)[:12]
    if not terms:
        return []
    match = " OR ".join(f'"{term}"' for term in terms)
    conn = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT {key} FROM {table} WHERE {table} MATCH ? "
            f"ORDER BY bm25({table}) LIMIT ?",
            (match, top_k),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def _in_pg_match(dsn: str, table: str, key: str, query: str, ids: list[str], term_limit: int) -> int:
    terms = _extract_keywords(query)[:term_limit]
    if not terms or not ids:
        return 0
    ts_query = " | ".join(terms)
    found = 0
    with pg_connection(dsn) as pg:
        for value in ids:
            row = pg.execute(
                f"SELECT 1 FROM {table} WHERE {key} = %s "
                "AND search_vector @@ to_tsquery('english', %s)",
                (value, ts_query),
            ).fetchone()
            if row:
                found += 1
    return found


def _score(a: list[str], b: list[str]) -> dict:
    sa, sb = set(a), set(b)
    union = len(sa | sb)
    common = len(sa & sb)
    return {
        "sqlite_top": a,
        "pg_top": b,
        "common": common,
        "jaccard": (common / union) if union else 1.0,
        "sqlite_top_in_pg": len(sa & sb),
        "pg_top_in_sqlite": len(sb & sa),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# FTS Shadow Compare",
        "",
        f"> queries: {report.get('queries')}  ",
        f"> top_k: {report.get('top_k')}  ",
        f"> paragraph avg jaccard: {report['paragraph']['avg_jaccard']:.3f}  ",
        f"> paragraph avg match recall: {report['paragraph']['avg_match_recall']:.3f}  ",
        f"> summary avg jaccard: {report['summary']['avg_jaccard']:.3f}  ",
        f"> summary avg match recall: {report['summary']['avg_match_recall']:.3f}",
        "",
        "## Paragraph",
        "",
        "| case | common | jaccard | sqlite_top_in_pg | sqlite_top_in_pg_match |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["paragraph"]["cases"]:
        lines.append(
            f"| {row['id']} | {row['common']} | {row['jaccard']:.3f} | {row['sqlite_top_in_pg']} | {row['sqlite_top_in_pg_match']} |"
        )
    lines += [
        "",
        "## Summary",
        "",
        "| case | common | jaccard | sqlite_top_in_pg | sqlite_top_in_pg_match |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["summary"]["cases"]:
        lines.append(
            f"| {row['id']} | {row['common']} | {row['jaccard']:.3f} | {row['sqlite_top_in_pg']} | {row['sqlite_top_in_pg_match']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--queries", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--term-limit", type=int, default=6)
    parser.add_argument("--ranker", choices=("rank", "rank_cd"), default="rank")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-shadow.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-shadow.md"))
    args = parser.parse_args()
    if not args.pg_dsn:
        print("--pg-dsn is required", file=sys.stderr)
        return 2
    cases = json.loads(Path(args.queries).read_text(encoding="utf-8")).get("cases") or []
    if args.limit:
        cases = cases[: args.limit]
    paragraph_rows, summary_rows = [], []
    para_fts = PGParagraphFTS(args.pg_dsn, ranker=args.ranker)
    summary_fts = PGSummaryFTS(args.pg_dsn, ranker=args.ranker)
    try:
        for case in cases:
            print(f"[{case['case_id']}]", flush=True)
            q = case["query"]
            sqlite_p = _sqlite_ids(args.db, "paragraphs_fts", "para_id", q, args.top_k)
            pg_p = [h.para_id for h in para_fts.search(q, top_k=args.top_k, term_limit=args.term_limit)]
            sqlite_s = _sqlite_ids(args.db, "summaries_fts", "summary_id", q, args.top_k)
            pg_s = [h.summary_id for h in summary_fts.search(q, top_k=args.top_k, term_limit=args.term_limit)]
            paragraph_rows.append({
                "id": case["case_id"],
                **_score(sqlite_p, pg_p),
                "sqlite_top_in_pg_match": _in_pg_match(
                    args.pg_dsn, "paragraphs", "para_id", q, sqlite_p, args.term_limit
                ),
            })
            summary_rows.append({
                "id": case["case_id"],
                **_score(sqlite_s, pg_s),
                "sqlite_top_in_pg_match": _in_pg_match(
                    args.pg_dsn, "summaries", "summary_id", q, sqlite_s, args.term_limit
                ),
            })
    finally:
        close_pools()
    report = {
        "queries": len(cases),
        "top_k": args.top_k,
        "paragraph": {
            "avg_jaccard": sum(r["jaccard"] for r in paragraph_rows) / max(len(paragraph_rows), 1),
            "avg_match_recall": sum(r["sqlite_top_in_pg_match"] for r in paragraph_rows) / max(len(paragraph_rows) * args.top_k, 1),
            "cases": paragraph_rows,
        },
        "summary": {
            "avg_jaccard": sum(r["jaccard"] for r in summary_rows) / max(len(summary_rows), 1),
            "avg_match_recall": sum(r["sqlite_top_in_pg_match"] for r in summary_rows) / max(len(summary_rows) * args.top_k, 1),
            "cases": summary_rows,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.out_md).write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"queries": report["queries"], "paragraph": report["paragraph"]["avg_jaccard"], "summary": report["summary"]["avg_jaccard"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
