"""Build claim–evidence links from citation sentences.

For a sentence that cites another paper, the best-matching sentence in the
cited paper is stored as evidence. This is a heuristic bridge; the confidence
is the token overlap.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from build_db.claims_schema import migrate

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
TOKEN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set:
    return {t.lower() for t in TOKEN.findall(text or "") if len(t) > 2}


def _load_paper_tokens(conn, paper_id: str) -> List[tuple]:
    rows = conn.execute(
        "SELECT sentence_id, text FROM sentences WHERE paper_id = ? "
        "AND length(text) BETWEEN 40 AND 400 LIMIT 200",
        (paper_id,),
    ).fetchall()
    return [(sentence_id, _tokens(text)) for sentence_id, text in rows]


def _best_evidence(
    conn, paper_id: str, claim_text: str, cache: Optional[Dict[str, List[tuple]]] = None
) -> Optional[tuple]:
    claim_tokens = _tokens(claim_text)
    if not claim_tokens:
        return None
    cache = cache if cache is not None else {}
    if paper_id not in cache:
        cache[paper_id] = _load_paper_tokens(conn, paper_id)
    best = None
    best_score = 0.0
    for sentence_id, tokens in cache[paper_id]:
        score = len(claim_tokens & tokens) / len(claim_tokens)
        if score > best_score:
            best, best_score = sentence_id, score
    if best and best_score > 0:
        return best, best_score
    return None


def build(db_path: Path | str = DEFAULT_DB, limit: int = 5000) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = {"claims": 0, "evidence": 0}
    migrate(db_path)
    try:
        rows = conn.execute(
            """
            SELECT sl.sentence_id, sl.intent, s.paper_id, s.text AS claim_text,
                   p.paper_id AS cited_paper
            FROM sentence_links sl
            JOIN sentences s ON s.sentence_id = sl.sentence_id
            JOIN citations c ON c.citation_id = sl.target_id
            JOIN papers p ON lower(p.doi) = lower(c.doi) AND p.doi != ''
            WHERE sl.target_type = 'citation' AND p.paper_id != s.paper_id
            GROUP BY sl.sentence_id, p.paper_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        cache: Dict[str, List[tuple]] = {}
        for row in rows:
            claim_id = f"claim_{row['sentence_id']}_{row['cited_paper']}"
            conn.execute(
                "INSERT OR IGNORE INTO claims "
                "(claim_id, paper_id, sentence_id, claim_text, claim_type, created_at) "
                "VALUES (?, ?, ?, ?, 'statement', CURRENT_TIMESTAMP)",
                (claim_id, row["paper_id"], row["sentence_id"], row["claim_text"]),
            )
            best = _best_evidence(conn, row["cited_paper"], row["claim_text"], cache)
            if best:
                evidence_id, score = best
                conn.execute(
                    "INSERT OR REPLACE INTO claim_evidence "
                    "(claim_id, evidence_sentence_id, relation, confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (claim_id, evidence_id, row["intent"] or "mention", round(score, 3)),
                )
                stats["evidence"] += 1
            stats["claims"] += 1
        conn.commit()
    finally:
        conn.close()
    return stats


def claims_for_paper(conn: sqlite3.Connection, paper_id: str) -> List[Dict]:
    rows = conn.execute(
        "SELECT claim_id, sentence_id, claim_text, claim_type FROM claims "
        "WHERE paper_id = ? ORDER BY claim_id",
        (paper_id,),
    ).fetchall()
    out = []
    for claim_id, sentence_id, text, claim_type in rows:
        evidence = conn.execute(
            "SELECT evidence_sentence_id, relation, confidence FROM claim_evidence "
            "WHERE claim_id = ? ORDER BY confidence DESC",
            (claim_id,),
        ).fetchall()
        out.append(
            {
                "claim_id": claim_id,
                "sentence_id": sentence_id,
                "text": text,
                "type": claim_type,
                "evidence": [
                    {"sentence_id": sid, "relation": rel, "confidence": conf}
                    for sid, rel, conf in evidence
                ],
            }
        )
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    print(build(args.db, args.limit))
