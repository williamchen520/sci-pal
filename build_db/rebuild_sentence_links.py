"""Rebuild sentence-level links with geometry.

For every sentence we detect citation markers (``[1]``, ``[2,3]``) and
figure/table mentions (``Fig. 1``, ``Table 2``) and resolve them against the
paper's ``citations`` / ``figures`` / ``tables`` rows.

The link always carries the sentence ``page`` + ``bbox``; when GROBID in-text
mentions exist for the same reference number, the mention's own page/bbox is
used instead (higher confidence).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from build_db.mention_patterns import figure_mentions, table_mentions
from services.search.citation_intent import classify

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*[,\-–]\s*\d{1,3})*)\]")
FIG_RE = re.compile(r"\b(?:Fig(?:ure)?\.?)\s*(\d{1,3}[A-Za-z]?)")
TABLE_RE = re.compile(r"\bTable\s*(\d{1,3}[A-Za-z]?)")


def _ref_numbers(match: str) -> List[str]:
    numbers: List[str] = []
    for part in re.split(r"[,]", match):
        part = part.strip()
        if re.fullmatch(r"\d+", part):
            numbers.append(part)
            continue
        rng = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if rng:
            start, end = int(rng.group(1)), int(rng.group(2))
            numbers.extend(str(n) for n in range(start, min(end, start + 50) + 1))
    return numbers


def _mention_bbox_top_left(bbox: str, page_height: float) -> str:
    """GROBID coords use bottom-left origin; convert to top-left."""
    try:
        x0, y0, x1, y1 = [float(v) for v in bbox.split(",")]
    except (TypeError, ValueError):
        return bbox
    top = page_height - y1
    bottom = page_height - y0
    return f"{x0:.2f},{top:.2f},{x1:.2f},{bottom:.2f}"


def build_for_paper(db_path: Path | str, paper_id: str) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    stats = {"citations": 0, "figures": 0, "tables": 0, "sentences": 0}
    try:
        sentences = conn.execute(
            "SELECT sentence_id, para_id, text, page, bbox, section_id "
            "FROM sentences WHERE paper_id = ? ORDER BY sequence",
            (paper_id,),
        ).fetchall()
        if not sentences:
            return stats

        cite_map = {
            str(row["ref_number"]).strip(): row["citation_id"]
            for row in conn.execute(
                "SELECT citation_id, ref_number FROM citations WHERE paper_id = ?",
                (paper_id,),
            )
            if row["ref_number"] is not None
        }
        fig_map = {
            str(row["fig_number"]).replace("Figure", "").replace("Fig", "").strip(): row["fig_id"]
            for row in conn.execute(
                "SELECT fig_id, fig_number FROM figures WHERE paper_id = ?", (paper_id,)
            )
            if row["fig_number"]
        }
        table_map = {
            str(row["table_number"]).replace("Table", "").strip(): row["table_id"]
            for row in conn.execute(
                "SELECT table_id, table_number FROM tables WHERE paper_id = ?", (paper_id,)
            )
            if row["table_number"]
        }
        mentions = {}
        for row in conn.execute(
            "SELECT ref_number, page, bbox FROM citation_mentions WHERE paper_id = ?",
            (paper_id,),
        ):
            if row["ref_number"]:
                mentions[str(row["ref_number"]).strip()] = (row["page"], row["bbox"])

        page_heights: Dict[int, float] = {}
        try:
            import fitz

            filename = conn.execute(
                "SELECT filename FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            documents = Path(db_path).resolve().parent.parent / "documents"
            pdf_path = documents / filename[0] if filename else None
            if pdf_path and pdf_path.exists():
                with fitz.open(str(pdf_path)) as doc:
                    page_heights = {i + 1: page.rect.height for i, page in enumerate(doc)}
        except Exception:  # noqa: BLE001
            page_heights = {}

        conn.execute("DELETE FROM sentence_links WHERE paper_id = ?", (paper_id,))

        def add_link(sentence, target_type: str, target_id: str, relation: str,
                     page, bbox, source: str, confidence: float,
                     intent: str = "") -> None:
            link_id = f"link_{sentence['sentence_id']}_{target_type}_{target_id}"
            conn.execute(
                "INSERT OR REPLACE INTO sentence_links "
                "(link_id, sentence_id, para_id, paper_id, source_type, target_type, "
                " target_id, relation, page, bbox, source, confidence, intent) "
                "VALUES (?, ?, ?, ?, 'sentence', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    link_id,
                    sentence["sentence_id"],
                    sentence["para_id"],
                    paper_id,
                    target_type,
                    target_id,
                    relation,
                    page,
                    bbox,
                    source,
                    confidence,
                    intent,
                ),
            )

        for sentence in sentences:
            stats["sentences"] += 1
            text = sentence["text"] or ""

            for marker in CITE_RE.finditer(text):
                for number in _ref_numbers(marker.group(1)):
                    citation_id = cite_map.get(number)
                    if not citation_id:
                        continue
                    page, bbox = mentions.get(number, (sentence["page"], sentence["bbox"]))
                    source = "grobid" if number in mentions else "regex"
                    if source == "grobid" and bbox and page in page_heights:
                        bbox = _mention_bbox_top_left(bbox, page_heights[page])
                    confidence = 0.9 if source == "grobid" else 0.6
                    add_link(
                        sentence, "citation", citation_id, "cites", page, bbox,
                        source, confidence, intent=classify(text),
                    )
                    stats["citations"] += 1

            for number, _ in figure_mentions(text):
                number = number.strip()
                fig_id = fig_map.get(number) or fig_map.get(number.rstrip("abcdefghijklmnopqrstuvwxyz"))
                if fig_id:
                    add_link(sentence, "figure", fig_id, "mentions",
                             sentence["page"], sentence["bbox"], "regex", 0.6)
                    stats["figures"] += 1

            for number, _ in table_mentions(text):
                number = number.strip()
                table_id = table_map.get(number) or table_map.get(number.rstrip("abcdefghijklmnopqrstuvwxyz"))
                if table_id:
                    add_link(sentence, "table", table_id, "mentions",
                             sentence["page"], sentence["bbox"], "regex", 0.6)
                    stats["tables"] += 1

        conn.commit()
    finally:
        conn.close()
    return stats


def build_all(db_path: Path | str = DEFAULT_DB, limit: int = 0) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    papers = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT s.paper_id FROM sentences s "
            "JOIN papers p ON p.paper_id = s.paper_id "
            "WHERE COALESCE(p.parse_engine, '') != 'xml'"
        )
    ]
    conn.close()
    total = {"papers": 0, "sentences": 0, "citations": 0, "figures": 0, "tables": 0}
    for paper_id in papers:
        stats = build_for_paper(db_path, paper_id)
        if not stats["sentences"]:
            continue
        total["papers"] += 1
        for key in ("sentences", "citations", "figures", "tables"):
            total[key] += stats[key]
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
        print(build_for_paper(args.db, args.paper_id))
    else:
        print(build_all(args.db, limit=args.limit))
