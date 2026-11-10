"""Audit the independent rebuild database before building vectors."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.pg_pool import pg_connection  # noqa: E402

CHECKS = {
    "sections_missing_parent": (
        "SELECT count(*) AS n FROM sections c LEFT JOIN sections p "
        "ON p.section_id=c.parent_id AND p.paper_id=c.paper_id "
        "WHERE c.depth > 1 AND p.section_id IS NULL"
    ),
    "sections_wrong_depth": (
        "SELECT count(*) AS n FROM sections c JOIN sections p ON p.section_id=c.parent_id "
        "WHERE c.depth != p.depth + 1"
    ),
    "sections_self_parent": "SELECT count(*) AS n FROM sections WHERE section_id=parent_id",
    "paragraphs_missing_section": (
        "SELECT count(*) AS n FROM paragraphs pa LEFT JOIN sections s "
        "ON s.section_id=pa.section_id AND s.paper_id=pa.paper_id "
        "WHERE pa.section_id IS NOT NULL AND s.section_id IS NULL"
    ),
    "paragraphs_missing_paper": (
        "SELECT count(*) AS n FROM paragraphs pa LEFT JOIN papers p ON p.paper_id=pa.paper_id "
        "WHERE p.paper_id IS NULL"
    ),
    "sentences_missing_paragraph": (
        "SELECT count(*) AS n FROM sentences se LEFT JOIN paragraphs pa ON pa.para_id=se.para_id "
        "WHERE pa.para_id IS NULL"
    ),
    "sentences_missing_paper": (
        "SELECT count(*) AS n FROM sentences se LEFT JOIN papers p ON p.paper_id=se.paper_id "
        "WHERE p.paper_id IS NULL"
    ),
    "papers_without_paragraphs": (
        "SELECT count(*) AS n FROM papers p WHERE NOT EXISTS "
        "(SELECT 1 FROM paragraphs pa WHERE pa.paper_id=p.paper_id)"
    ),
    "empty_paragraphs": "SELECT count(*) AS n FROM paragraphs WHERE coalesce(trim(text),'')=''",
    "empty_sentences": "SELECT count(*) AS n FROM sentences WHERE coalesce(trim(text),'')=''",
}

COUNTS = ["papers", "sections", "paragraphs", "sentences", "figures", "citations", "sentence_links"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "rebuild_audit.json"))
    args = parser.parse_args()
    pg = pg_connection()
    try:
        counts = {}
        for table in COUNTS:
            try:
                counts[table] = pg.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            except Exception:
                counts[table] = None
        results = {}
        for name, sql in CHECKS.items():
            try:
                results[name] = pg.execute(sql).fetchone()["n"]
            except Exception as exc:  # noqa: BLE001
                results[name] = f"ERROR: {exc}"
    finally:
        pg.close()
    critical = {k: v for k, v in results.items() if isinstance(v, int) and v}
    report = {"counts": counts, "checks": results, "critical": critical}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
