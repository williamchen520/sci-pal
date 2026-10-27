"""Sentence geometry: split paragraphs into sentences and give each a bbox.

Sentence bbox strategy (PDF only):

1. normalize the paragraph bbox to top-left origin;
2. ``page.search_for(sentence_text)`` clipped to the paragraph rect;
3. fall back to the paragraph bbox when the text cannot be located
   (scanned PDFs / ligature differences), marking ``bbox_source``.

The paragraph-level bbox comes from Docling provenance (``doc_items[*].prov``)
or from legacy rows. XML papers have no coordinates and are skipped.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[\(\"'])")


def split_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    parts = SENT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_bbox(value: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not value:
        return None
    try:
        parts = [float(x) for x in str(value).split(",")]
    except (TypeError, ValueError):
        return None
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def bbox_union(boxes: List[Tuple[float, float, float, float]]):
    if not boxes:
        return None
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[2] for b in boxes)
    bottom = max(b[3] for b in boxes)
    return left, top, right, bottom


def to_topleft(
    bbox: Tuple[float, float, float, float], page_height: float
) -> Tuple[float, float, float, float]:
    """Docling uses bottom-left origin; store everything top-left."""
    l, t, r, b = bbox
    if t > b:  # bottom-left origin
        return l, page_height - t, r, page_height - b
    return l, t, r, b


def _locate_in_doc(doc, text: str, max_pages: int = 30):
    """Search all pages (used when paragraph page is unknown)."""
    candidates = [text]
    if len(text) > 120:
        candidates.append(text[:120])
    if len(text) > 60:
        candidates.append(text[:60])
    for page_index in range(min(doc.page_count, max_pages)):
        page = doc[page_index]
        for candidate in candidates:
            try:
                rects = page.search_for(candidate)
            except Exception:  # noqa: BLE001
                continue
            if rects:
                boxes = [(r.x0, r.y0, r.x1, r.y1) for r in rects]
                return page_index + 1, bbox_union(boxes)
    return None, None


def _locate_sentence(page, text: str, clip) -> Optional[Tuple[float, float, float, float]]:
    candidates = [text]
    if len(text) > 120:
        candidates.append(text[:120])
    if len(text) > 60:
        candidates.append(text[:60])
    for candidate in candidates:
        try:
            rects = page.search_for(candidate, clip=clip, quads=False)
        except Exception:  # noqa: BLE001
            continue
        if rects:
            boxes = [(r.x0, r.y0, r.x1, r.y1) for r in rects]
            return bbox_union(boxes)
    return None


def build_sentences_for_paper(
    db_path: Path | str, paper_id: str, pdf_path: Path | str
) -> Dict[str, Any]:
    """Rebuild sentences for one paper with per-sentence bbox."""
    import fitz  # PyMuPDF

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = {"sentences": 0, "with_bbox": 0, "fallback": 0, "skipped": 0}
    try:
        rows = conn.execute(
            "SELECT para_id, text, page, bbox, section_id FROM paragraphs "
            "WHERE paper_id = ? ORDER BY sequence",
            (paper_id,),
        ).fetchall()
        if not rows:
            return stats

        doc = fitz.open(str(pdf_path))
        conn.execute("DELETE FROM sentences WHERE paper_id = ?", (paper_id,))
        try:
            for row in rows:
                para_text = row["text"] or ""
                sentences = split_sentences(para_text)
                if not sentences:
                    continue
                page_no = row["page"]
                para_bbox = parse_bbox(row["bbox"])
                page = None
                if page_no and 1 <= page_no <= doc.page_count:
                    page = doc[page_no - 1]
                clip = None
                if page is not None and para_bbox:
                    tl = to_topleft(para_bbox, page.rect.height)
                    clip = fitz.Rect(*tl)

                offset = 0
                for index, sentence in enumerate(sentences, 1):
                    start = para_text.find(sentence, offset)
                    if start < 0:
                        start = offset
                    end = start + len(sentence)
                    offset = end

                    bbox = None
                    source = "none"
                    if page is None:
                        found_page, found_bbox = _locate_in_doc(doc, sentence)
                        if found_bbox is not None:
                            page_no = found_page
                            bbox = found_bbox
                            source = "search"
                    if page is not None:
                        bbox = _locate_sentence(page, sentence, clip)
                        if bbox is not None:
                            source = "search"
                        elif clip is not None:
                            bbox = tuple(clip)
                            source = "paragraph"
                    if bbox is None and para_bbox and page is not None:
                        bbox = to_topleft(para_bbox, page.rect.height)
                        source = "paragraph"

                    sentence_id = f"{row['para_id']}_sent_{index:03d}"
                    bbox_text = (
                        ",".join(f"{v:.2f}" for v in bbox) if bbox else None
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO sentences
                            (sentence_id, para_id, paper_id, text, sequence,
                             page, bbox, section_id, char_start, char_end)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sentence_id,
                            row["para_id"],
                            paper_id,
                            sentence,
                            index,
                            page_no,
                            bbox_text,
                            row["section_id"],
                            start,
                            end,
                        ),
                    )
                    stats["sentences"] += 1
                    if bbox_text:
                        stats["with_bbox"] += 1
                    if source == "paragraph":
                        stats["fallback"] += 1
        finally:
            doc.close()
        conn.commit()
    finally:
        conn.close()
    return stats


def build_for_papers(db_path: Path | str, limit: int = 0, only_pdf: bool = True) -> Dict[str, int]:
    """Build sentences for papers that have a local PDF and paragraphs."""
    documents = Path(db_path).resolve().parent.parent / "documents"
    conn = sqlite3.connect(str(db_path))
    total = {"papers": 0, "sentences": 0, "with_bbox": 0, "fallback": 0}
    try:
        rows = conn.execute(
            "SELECT DISTINCT p.paper_id, p.filename FROM papers p "
            "JOIN paragraphs pa ON pa.paper_id = p.paper_id "
            "WHERE p.filename LIKE '%.pdf' ORDER BY p.paper_id"
        ).fetchall()
    finally:
        conn.close()

    for paper_id, filename in rows:
        pdf_path = documents / filename
        if not pdf_path.exists():
            continue
        stats = build_sentences_for_paper(db_path, paper_id, pdf_path)
        if not stats["sentences"]:
            continue
        total["papers"] += 1
        total["sentences"] += stats["sentences"]
        total["with_bbox"] += stats["with_bbox"]
        total["fallback"] += stats["fallback"]
        print(
            f"{filename}: {stats['sentences']} sentences, "
            f"{stats['with_bbox']} bbox, {stats['fallback']} paragraph-fallback"
        )
        if limit and total["papers"] >= limit:
            break
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--paper-id")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.paper_id:
        conn = sqlite3.connect(args.db)
        filename = conn.execute(
            "SELECT filename FROM papers WHERE paper_id = ?", (args.paper_id,)
        ).fetchone()[0]
        conn.close()
        doc = Path(args.db).resolve().parent.parent / "documents" / filename
        print(build_sentences_for_paper(args.db, args.paper_id, doc))
    else:
        print(build_for_papers(args.db, limit=args.limit))
