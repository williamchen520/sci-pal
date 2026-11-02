#!/usr/bin/env python3
"""Backfill missing paper and section-summary vectors.

Papers: embed papers without a Chroma row.
Sections: create missing summaries (title + first paragraph, if any), write
SQLite/PostgreSQL, then embed them.

Run with --dry-run first; stop the API before applying.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("G:/sciPal_deploy/data/research.db")
DEFAULT_CHROMA = Path("G:/sciPal_deploy/data/chroma")
DEFAULT_MODEL = "D:/models/models/BAAI--bge-base-en-v1.5"


def _summary_text(title: str, body: str | None) -> str:
    title = (title or "").strip()
    if not body:
        return title or "Untitled section"
    body = " ".join(body.split())
    for end in (". ", "。", "! ", "? "):
        index = body.find(end)
        if 0 < index < 260:
            body = body[: index + 1]
            break
    else:
        body = body[:260]
    return (title + " " + body).strip()[:600]


def run(args) -> dict:
    import chromadb
    import torch
    from sentence_transformers import SentenceTransformer

    conn = sqlite3.connect(str(args.sqlite))
    conn.row_factory = sqlite3.Row
    client = chromadb.PersistentClient(path=str(args.chroma))

    papers_missing: list[dict] = []
    paper_col = client.get_collection("papers") if "papers" in {c.name for c in client.list_collections()} else None
    if paper_col:
        existing = set(paper_col.get(include=[])["ids"])
        for row in conn.execute("SELECT paper_id, title, authors, journal, year FROM papers"):
            if row["paper_id"] not in existing and (row["title"] or "").strip():
                papers_missing.append(dict(row))

    sec_col = client.get_collection("section_summaries") if "section_summaries" in {c.name for c in client.list_collections()} else None
    section_missing: list[dict] = []
    if sec_col:
        existing = set(sec_col.get(include=[])["ids"])
        summary_by_section = {
            row["section_id"]: dict(row)
            for row in conn.execute(
                "SELECT summary_id, paper_id, section_id, title, text FROM summaries"
            )
        }
        for row in conn.execute(
            "SELECT section_id, paper_id, title FROM sections ORDER BY paper_id, seq"
        ):
            sid = row["section_id"]
            rec = summary_by_section.get(sid)
            if rec:
                if rec["summary_id"] in existing:
                    continue
                rec["new"] = False
                rec["id"] = rec["summary_id"]
                section_missing.append(rec)
                continue
            summary_id = f"sum_{sid}"
            if summary_id in existing:
                continue
            body = conn.execute(
                "SELECT text FROM paragraphs WHERE section_id=? "
                "AND text IS NOT NULL AND length(trim(text)) > 20 ORDER BY sequence LIMIT 1",
                (sid,),
            ).fetchone()
            section_missing.append(
                {
                    "summary_id": summary_id,
                    "id": summary_id,
                    "paper_id": row["paper_id"],
                    "section_id": sid,
                    "title": row["title"] or "",
                    "text": _summary_text(row["title"] or "", body[0] if body else None),
                    "new": True,
                }
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "papers_missing": len(papers_missing),
        "sections_missing": len(section_missing),
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        report["paper_sample"] = [r["paper_id"] for r in papers_missing[:5]]
        report["section_sample"] = [r["summary_id"] for r in section_missing[:5]]
        conn.close()
        return report

    model_path = args.model or os.environ.get("SCIPAL_EMBEDDING_MODEL") or DEFAULT_MODEL
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = SentenceTransformer(model_path, device=device)

    def encode_upsert(collection, rows, text_key: str, metadata):
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            texts = [row[text_key] for row in batch]
            embeddings = model.encode(
                texts, batch_size=args.batch_size, show_progress_bar=False
            )
            collection.upsert(
                ids=[row["id"] for row in batch],
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=[metadata(row) for row in batch],
            )
            print(f"upserted {min(start + len(batch), len(rows))}/{len(rows)}", flush=True)

    if paper_col and papers_missing:
        paper_by_id = {p["paper_id"]: p for p in papers_missing}
        rows = [
            {
                "id": p["paper_id"],
                "text": f"{p['title']}. {p['authors'] or ''}",
            }
            for p in papers_missing
        ]
        encode_upsert(
            paper_col,
            rows,
            "text",
            lambda p: {
                "paper_id": p["id"],
                "year": paper_by_id[p["id"]]["year"] or 0,
                "journal": paper_by_id[p["id"]]["journal"] or "",
                "type": "paper",
            },
        )

    if sec_col and section_missing:
        now = datetime.now(timezone.utc).isoformat()
        for row in section_missing:
            if not row.get("new"):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO summaries "
                "(summary_id,paper_id,section_id,level,title,text,token_count,created_at,summary_source) "
                "VALUES (?,?,?,1,?,?,?,?,'extractive-backfill')",
                (
                    row["summary_id"], row["paper_id"], row["section_id"],
                    row["title"], row["text"], len(row["text"].split()), now,
                ),
            )
        conn.commit()
        if args.pg_dsn:
            import psycopg

            with psycopg.connect(args.pg_dsn) as pg:
                cur = pg.cursor()
                cur.executemany(
                    "INSERT INTO summaries "
                    "(summary_id,paper_id,section_id,level,title,text,token_count,created_at,summary_source) "
                    "VALUES (%s,%s,%s,1,%s,%s,%s,%s,'extractive-backfill') "
                    "ON CONFLICT (summary_id) DO UPDATE SET text=EXCLUDED.text, title=EXCLUDED.title",
                    [
                        (
                            row["summary_id"], row["paper_id"], row["section_id"],
                            row["title"], row["text"], len(row["text"].split()), now,
                        )
                        for row in section_missing if row.get("new")
                    ],
                )
                cur.close()
        encode_upsert(
            sec_col,
            section_missing,
            "text",
            lambda r: {
                "paper_id": r["paper_id"],
                "section_id": r["section_id"],
                "title": r["title"],
            },
        )
        report["summaries_inserted"] = len(section_missing)

    if args.pg_dsn:
        import psycopg

        rows = conn.execute(
            "SELECT summary_id,paper_id,section_id,level,title,text,token_count,created_at,summary_source "
            "FROM summaries"
        ).fetchall()
        with psycopg.connect(args.pg_dsn) as pg:
            cur = pg.cursor()
            cur.executemany(
                "INSERT INTO summaries "
                "(summary_id,paper_id,section_id,level,title,text,token_count,created_at,summary_source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (summary_id) DO UPDATE SET text=EXCLUDED.text, title=EXCLUDED.title",
                rows,
            )
            cur.close()
        report["pg_summaries_synced"] = len(rows)

    conn.close()
    report["papers_upserted"] = len(papers_missing)
    report["vectors_after"] = {
        "papers": paper_col.count() if paper_col else None,
        "section_summaries": sec_col.count() if sec_col else None,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = run(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
