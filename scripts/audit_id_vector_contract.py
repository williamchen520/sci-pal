#!/usr/bin/env python3
"""Read-only ID / vector contract audit.

Checks Chroma ids against SQLite/PostgreSQL ids, coverage, metadata and hierarchy.
Writes JSON/CSV reports only; never writes to the databases or Chroma.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "eval" / "plugins" / "retriever_queries.json"

# collection -> (db table, id column, description)
COLLECTIONS = {
    "paragraphs": ("paragraphs", "para_id"),
    "paragraphs_contextual": ("paragraphs", "para_id"),
    "papers": ("papers", "paper_id"),
    "figures": ("figures", "fig_id"),
    "tables": ("tables", "table_id"),
}


def _sqlite_ids(conn: sqlite3.Connection, table: str, column: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
    }


def _pg_ids(pg, table: str, column: str) -> set[str]:
    rows = pg.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
    return {str(row[0]) for row in rows}


def _format(identifier: str) -> str:
    if re.match(r"^para_paper_.+_\d{4}$", identifier):
        return "para_paper_*"
    if re.match(r"^paper_.+_para_\d{5}$", identifier):
        return "paper_*_para_*"
    if re.match(r"^sec_paper_.+_\d{4}$", identifier):
        return "sec_paper_*"
    if re.match(r"^paper_.+_sec_\d{4}$", identifier):
        return "paper_*_sec_*"
    if re.match(r"^sum_.+", identifier):
        return "sum_*"
    if "_sent_" in identifier:
        return "*_sent_*"
    return "other"


def _distribution(ids: set[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for identifier in ids:
        key = _format(identifier)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda item: -item[1]))


def _resolve_summary(summary_id: str, section_ids: set[str]) -> str | None:
    candidate = summary_id[4:] if summary_id.startswith("sum_") else summary_id
    if candidate in section_ids:
        return candidate
    return None


def _metadata_complete(meta: dict[str, Any], required: tuple[str, ...]) -> bool:
    # Presence is required; empty section/journal values are legitimate.
    return all(key in meta for key in required)


def _gold_sentence_check(sqlite: sqlite3.Connection, pg) -> dict[str, Any]:
    cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8")).get("cases", [])
    total = same = text_match = missing = 0
    for case in cases:
        for sentence_id in case.get("gold_sentence_ids") or []:
            total += 1
            row = sqlite.execute(
                "SELECT paper_id, text FROM sentences WHERE sentence_id=?", (sentence_id,)
            ).fetchone()
            if not row:
                missing += 1
                continue
            paper_id, text = row
            pg_row = pg.execute(
                "SELECT sentence_id FROM sentences WHERE sentence_id=%s", (sentence_id,)
            ).fetchone()
            if pg_row:
                same += 1
                continue
            pg_row = pg.execute(
                "SELECT sentence_id FROM sentences WHERE paper_id=%s AND text=%s LIMIT 1",
                (paper_id, text),
            ).fetchone()
            if pg_row:
                text_match += 1
            else:
                missing += 1
    return {
        "total": total,
        "same_id": same,
        "text_match_only": text_match,
        "missing": missing,
        "text_match_rate": round((same + text_match) / total, 4) if total else None,
    }


def _hierarchy(pg) -> dict[str, int]:
    checks = {
        "orphan_sections": """
            SELECT count(*) FROM sections s
            WHERE s.parent_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM sections p WHERE p.section_id=s.parent_id)
        """,
        "orphan_paragraphs": """
            SELECT count(*) FROM paragraphs p
            WHERE NOT EXISTS (SELECT 1 FROM papers x WHERE x.paper_id=p.paper_id)
               OR (p.section_id IS NOT NULL AND NOT EXISTS
                   (SELECT 1 FROM sections s WHERE s.section_id=p.section_id))
        """,
        "orphan_sentences": """
            SELECT count(*) FROM sentences s
            WHERE NOT EXISTS (SELECT 1 FROM papers x WHERE x.paper_id=s.paper_id)
               OR NOT EXISTS (SELECT 1 FROM paragraphs p WHERE p.para_id=s.para_id)
        """,
    }
    return {name: int(pg.execute(sql).fetchone()[0]) for name, sql in checks.items()}


def run(args) -> dict[str, Any]:
    import chromadb
    import psycopg

    sqlite = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    pg = psycopg.connect(args.pg_dsn)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sqlite": str(args.sqlite),
        "pg": "scipal_bench",
        "chroma": str(args.chroma),
        "collections": {},
        "ids": {},
        "id_formats": {},
        "hierarchy": {},
        "sentence_evidence": {},
        "verdict": "pass",
        "failures": [],
        "warnings": [],
    }
    try:
        sqlite_sets = {
            "papers": _sqlite_ids(sqlite, "papers", "paper_id"),
            "sections": _sqlite_ids(sqlite, "sections", "section_id"),
            "paragraphs": _sqlite_ids(sqlite, "paragraphs", "para_id"),
            "sentences": _sqlite_ids(sqlite, "sentences", "sentence_id"),
            "figures": _sqlite_ids(sqlite, "figures", "fig_id"),
            "tables": _sqlite_ids(sqlite, "tables", "table_id"),
        }
        pg_sets = {
            "papers": _pg_ids(pg, "papers", "paper_id"),
            "sections": _pg_ids(pg, "sections", "section_id"),
            "paragraphs": _pg_ids(pg, "paragraphs", "para_id"),
            "sentences": _pg_ids(pg, "sentences", "sentence_id"),
            "figures": _pg_ids(pg, "figures", "fig_id"),
            "tables": _pg_ids(pg, "tables", "table_id"),
        }
        for name in ("papers", "sections", "paragraphs", "sentences", "figures", "tables"):
            a, b = sqlite_sets[name], pg_sets[name]
            report["ids"][name] = {
                "sqlite": len(a),
                "pg": len(b),
                "same": len(a & b),
                "sqlite_only": len(a - b),
                "pg_only": len(b - a),
                "consistency": round(len(a & b) / len(a | b), 4) if a | b else 1.0,
            }
            report["id_formats"][name] = {
                "sqlite": _distribution(a),
                "pg": _distribution(b),
            }

        client = chromadb.PersistentClient(path=str(args.chroma))
        collections = {col.name for col in client.list_collections()}
        total_unique = total_resolved = 0
        csv_rows: list[dict[str, str]] = []
        for name, (table, column) in COLLECTIONS.items():
            if name not in collections:
                report["collections"][name] = {"missing": True}
                report["warnings"].append(f"collection missing: {name}")
                continue
            collection = client.get_collection(name)
            ids = collection.get(include=[])["ids"]
            unique = set(ids)
            db_ids = sqlite_sets[table]
            resolved = unique & db_ids
            orphan = unique - db_ids
            total_unique += len(unique)
            total_resolved += len(resolved)
            sample = collection.get(limit=args.sample, include=["metadatas"])
            required = {
                "paragraphs": ("paper_id", "section_l1", "section_l2"),
                "paragraphs_contextual": ("paper_id", "section_l1", "section_l2"),
                "papers": ("paper_id", "year", "journal"),
                "figures": ("paper_id", "page", "file_path"),
                "tables": ("paper_id", "page", "table_number"),
            }[name]
            complete = sum(
                1 for meta in (sample.get("metadatas") or []) if _metadata_complete(meta or {}, required)
            )
            report["collections"][name] = {
                "vector_total": len(ids),
                "vector_unique_ids": len(unique),
                "vector_resolved": len(resolved),
                "vector_orphan": len(orphan),
                "vector_duplicate_ids": len(ids) - len(unique),
                "db_total": len(db_ids),
                "db_with_vector": len(resolved),
                "db_coverage": round(len(resolved) / len(db_ids), 4) if db_ids else None,
                "resolution_rate": round(len(resolved) / len(unique), 4) if unique else 1.0,
                "metadata_sample": len(sample.get("metadatas") or []),
                "metadata_complete_rate": round(complete / len(sample["metadatas"]), 4)
                if sample.get("metadatas") else None,
            }
            for identifier in list(orphan)[: args.max_anomalies]:
                csv_rows.append(
                    {"collection": name, "vector_id": identifier, "status": "orphan", "db_table": table}
                )

        if "section_summaries" in collections:
            collection = client.get_collection("section_summaries")
            ids = collection.get(include=[])["ids"]
            unique = set(ids)
            section_ids = sqlite_sets["sections"]
            resolved = {i for i in unique if _resolve_summary(i, section_ids)}
            report["collections"]["section_summaries"] = {
                "vector_total": len(ids),
                "vector_unique_ids": len(unique),
                "vector_resolved": len(resolved),
                "vector_orphan": len(unique - resolved),
                "db_total": len(section_ids),
                "db_with_vector": len(resolved),
                "db_coverage": round(len(resolved) / len(section_ids), 4) if section_ids else None,
                "resolution_rate": round(len(resolved) / len(unique), 4) if unique else 1.0,
            }
            total_unique += len(unique)
            total_resolved += len(resolved)
        else:
            report["collections"]["section_summaries"] = {"missing": True}
            report["warnings"].append("collection missing: section_summaries")

        report["vector_resolution_rate"] = (
            round(total_resolved / total_unique, 4) if total_unique else None
        )
        report["hierarchy"] = _hierarchy(pg)
        report["sentence_evidence"] = _gold_sentence_check(sqlite, pg)

        if report["vector_resolution_rate"] is not None and report["vector_resolution_rate"] < 0.999:
            report["failures"].append("vector resolution < 99.9%")
        if report["collections"].get("section_summaries", {}).get("vector_orphan", 0):
            report["failures"].append("section summary orphan vectors")
        for name in ("sections", "paragraphs"):
            if report["ids"][name]["consistency"] < 1.0:
                report["failures"].append(f"{name} SQLite/PG id consistency < 100%")
        if report["sentence_evidence"].get("text_match_rate") != 1.0:
            report["failures"].append("sentence text match < 100%")
        for name, item in report["collections"].items():
            if item.get("metadata_complete_rate") is not None and item["metadata_complete_rate"] < 0.999:
                report["failures"].append(f"{name} metadata completeness < 99.9%")
            if item.get("db_coverage") is not None and item["db_coverage"] < 0.90:
                report["warnings"].append(f"{name} db coverage < 90%")
        if any(report["hierarchy"].values()):
            report["warnings"].append("hierarchy orphans present")

        report["verdict"] = "fail" if report["failures"] else ("warn" if report["warnings"] else "pass")
        if args.csv:
            Path(args.csv).write_text(
                "collection,vector_id,status,db_table\n"
                + "\n".join(
                    f'{row["collection"]},{row["vector_id"]},{row["status"]},{row["db_table"]}'
                    for row in csv_rows
                )
                + "\n",
                encoding="utf-8",
            )
        return report
    finally:
        sqlite.close()
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="G:/sciPal_deploy/data/research.db")
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--chroma", default="G:/sciPal_deploy/data/chroma")
    parser.add_argument("--out", default="")
    parser.add_argument("--csv", default="")
    parser.add_argument("--sample", type=int, default=5000)
    parser.add_argument("--max-anomalies", type=int, default=500)
    args = parser.parse_args()
    report = run(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("verdict", "failures", "warnings", "vector_resolution_rate")}, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
