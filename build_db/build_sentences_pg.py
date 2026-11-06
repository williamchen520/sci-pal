"""Rebuild sentences directly in PostgreSQL."""

from __future__ import annotations

import re
from typing import Dict

from services.db.pg_pool import pg_connection


def split_into_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def build_paper(pg, paper_id: str) -> Dict[str, int]:
    rows = pg.execute(
        "SELECT para_id, text, section_id FROM paragraphs WHERE paper_id=%s "
        "ORDER BY sequence, para_id",
        (paper_id,),
    ).fetchall()
    sentences = []
    for row in rows:
        para_id, text, section_id = row[0], row[1] or "", row[2]
        parts = split_into_sentences(text)
        offsets = []
        cursor = 0
        for part in parts:
            start = text.find(part, cursor)
            if start < 0:
                start = cursor
            offsets.append((start, start + len(part)))
            cursor = start + len(part)
        for index, part in enumerate(parts, 1):
            sentences.append(
                (
                    f"{para_id}_sent_{index:03d}",
                    para_id,
                    paper_id,
                    part,
                    index,
                    section_id,
                    offsets[index - 1][0],
                    offsets[index - 1][1],
                )
            )
    pg.execute("DELETE FROM sentences WHERE paper_id=%s", (paper_id,))
    if sentences:
        with pg.cursor() as cur:
            cur.executemany(
                "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,"
                "section_id,char_start,char_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                sentences,
            )
    return {"papers": 1, "sentences": len(sentences)}


def build_all(dsn: str = "") -> Dict[str, int]:
    pg = pg_connection(dsn)
    try:
        paper_ids = [
            row[0] for row in pg.execute("SELECT paper_id FROM papers").fetchall()
        ]
        totals = {"papers": 0, "sentences": 0}
        for paper_id in paper_ids:
            stats = build_paper(pg, paper_id)
            totals["papers"] += stats["papers"]
            totals["sentences"] += stats["sentences"]
            pg.commit()
        return totals
    finally:
        pg.close()
