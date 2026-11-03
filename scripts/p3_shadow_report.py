#!/usr/bin/env python3
"""Generate a P3 shadow-read report (SQLite snapshot vs PostgreSQL).

Read-only: compares row counts, key sets, sampled field values and optional FTS
queries. Writes JSON + Markdown for human review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.db.pg_pool import pg_connection  # noqa: E402
from services.db.shadow_read import ShadowReader  # noqa: E402

DEFAULT_TABLES = [
    ("papers", "paper_id"),
    ("sections", "section_id"),
    ("paragraphs", "para_id"),
    ("sentences", "sentence_id"),
    ("citations", "citation_id"),
    ("sentence_links", "link_id"),
    ("paper_links", "link_id"),
]


def parse_tables(value: str):
    if not value:
        return DEFAULT_TABLES
    out = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise SystemExit(f"table must be name:key, got {item!r}")
        table, key = item.split(":", 1)
        out.append((table.strip(), key.strip()))
    return out


def latest_snapshot(backups: Path) -> Path:
    candidates = sorted(
        (p for p in backups.glob("*.db") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no .db snapshot in {backups}")
    return candidates[0]


def render_markdown(report: dict) -> str:
    lines = [
        "# P3 Shadow Read Report",
        "",
        f"> generated_at: {report.get('generated_at', '')}  ",
        f"> source: `{report.get('source', '')}`  ",
        f"> status: **{report.get('status', '')}**  ",
        f"> ignored_fields: `{', '.join(report.get('ignored_fields') or [])}`",
        "",
        "## Tables",
        "",
        "| table | sqlite | postgres | common | missing_in_pg | extra_in_pg | field_diffs | status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.get("tables") or []:
        lines.append(
            f"| {item['table']} | {item['sqlite_rows']} | {item['postgres_rows']} | "
            f"{item['common_keys']} | {item['missing_in_pg']} | {item['extra_in_pg']} | "
            f"{item['field_diffs']} | {item['status']} |"
        )
    if report.get("fts"):
        lines += [
            "",
            "## FTS",
            "",
            "| query | common | sqlite_only | postgres_only | jaccard | status |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for item in report["fts"]:
            lines.append(
                f"| {item['query']} | {item['common']} | {item['sqlite_only']} | "
                f"{item['postgres_only']} | {item['jaccard']:.3f} | {item['status']} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="", help="SQLite snapshot; default latest backups/*.db")
    parser.add_argument("--backups", default=str(ROOT / "backups"))
    parser.add_argument("--pg-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--tables", default="", help="comma-separated table:key list")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--fts-query", action="append", default=[])
    parser.add_argument("--fts-limit", type=int, default=10)
    parser.add_argument("--out", default=str(ROOT / "docs" / "PostgreSQL迁移-P3-shadow.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "PostgreSQL迁移-P3-shadow.md"))
    parser.add_argument(
        "--ignore-fields",
        default="created_at,updated_at",
        help="comma-separated columns excluded from field diffs (timestamps)",
    )
    args = parser.parse_args()

    if not args.pg_dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    source = Path(args.source) if args.source else latest_snapshot(Path(args.backups))
    if source.resolve() == (ROOT / "data" / "research.db").resolve():
        print("refusing live data/research.db; use a snapshot", file=sys.stderr)
        return 2

    tables = parse_tables(args.tables)
    ignore_fields = tuple(x.strip() for x in args.ignore_fields.split(",") if x.strip())
    with pg_connection(args.pg_dsn) as pg:
        report = ShadowReader(source, pg, sample_limit=5, ignore_fields=ignore_fields).run(
            tables,
            limit=args.limit,
            fts_queries=args.fts_query,
            fts_limit=args.fts_limit,
        )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["source"] = str(source)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.out_md).write_text(render_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "source": str(source), "out": args.out}, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
