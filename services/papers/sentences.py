"""Build the paper -> section -> paragraph -> sentence tree."""

from __future__ import annotations

from typing import Any

import pysbd

SEGMENTER = pysbd.Segmenter(language="en", clean=False)


def split_sentences(text: str) -> list[dict[str, Any]]:
    """Split one paragraph and preserve character offsets."""
    source = text or ""
    segments = [segment.strip() for segment in SEGMENTER.segment(source) if segment.strip()]
    if not segments:
        stripped = source.strip()
        if not stripped:
            return []
        start = source.find(stripped)
        return [{"text": stripped, "char_start": start, "char_end": start + len(stripped)}]
    rows = []
    cursor = 0
    for segment in segments:
        start = source.find(segment, cursor)
        if start < 0:
            start = source.find(segment)
        if start < 0:
            continue
        end = start + len(segment)
        rows.append({"text": segment, "char_start": start, "char_end": end})
        cursor = end
    return rows


def paragraph_sentences(paper_id: str, paragraph: dict[str, Any]) -> list[dict[str, Any]]:
    para_id = str(paragraph["para_id"])
    rows = []
    for index, sentence in enumerate(split_sentences(str(paragraph.get("text") or "")), 1):
        rows.append(
            {
                "sentence_id": f"{para_id}_sent_{index:03d}",
                "para_id": para_id,
                "paper_id": paper_id,
                "text": sentence["text"],
                "sequence": index,
                "page": paragraph.get("page"),
                "bbox": paragraph.get("bbox"),
                "section_id": paragraph.get("section_id"),
                "char_start": sentence["char_start"],
                "char_end": sentence["char_end"],
            }
        )
    return rows


def build_for_paper(*, paper_id: str, dsn: str, replace: bool = True) -> dict[str, int]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        paragraphs = conn.execute(
            "SELECT para_id, paper_id, section_id, page, bbox, text "
            "FROM paragraphs WHERE paper_id=%s ORDER BY sequence",
            (paper_id,),
        ).fetchall()
        columns = ["para_id", "paper_id", "section_id", "page", "bbox", "text"]
        rows = [dict(zip(columns, row)) for row in paragraphs]
        if replace:
            conn.execute("DELETE FROM sentences WHERE paper_id=%s", (paper_id,))
        inserted = 0
        for paragraph in rows:
            for sentence in paragraph_sentences(paper_id, paragraph):
                conn.execute(
                    """
                    INSERT INTO sentences
                      (sentence_id,para_id,paper_id,text,sequence,page,bbox,section_id,char_start,char_end)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (sentence_id) DO UPDATE SET
                      text=EXCLUDED.text,
                      sequence=EXCLUDED.sequence,
                      page=EXCLUDED.page,
                      bbox=EXCLUDED.bbox,
                      section_id=EXCLUDED.section_id,
                      char_start=EXCLUDED.char_start,
                      char_end=EXCLUDED.char_end
                    """,
                    (
                        sentence["sentence_id"],
                        sentence["para_id"],
                        sentence["paper_id"],
                        sentence["text"],
                        sentence["sequence"],
                        sentence["page"],
                        sentence["bbox"],
                        sentence["section_id"],
                        sentence["char_start"],
                        sentence["char_end"],
                    ),
                )
                inserted += 1
        conn.commit()
    return {"paragraphs": len(rows), "sentences": inserted}
