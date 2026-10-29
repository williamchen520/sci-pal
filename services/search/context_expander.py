"""
Small-to-big (parent document) retrieval with structural section paths.

Retrieval stays precise at the paragraph level, but the LLM is handed the
surrounding parent context (the whole section, or a bounded window when the
section is too large), plus the explicit section path from ``sections``.

Two expansion modes:
  - "section": group hits by section_id (fallback: legacy section_level1/2),
               return the whole section in reading order; matched paragraphs
               (or their best-matching sentences) are marked.
  - "window":  a fixed number of paragraphs before/after each hit.

The parent unit carries ``section_path`` (root → leaf titles) so the caller can
show "Chapter 3 › 3.2 Efficacy" instead of a bare paragraph.
"""
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from services.search.sentence_roles import pick_anchor

from services.search.boilerplate_filter import clean_boilerplate

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

HIT_START = "►"
HIT_END = "◄"

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


class ContextExpander:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def _row_dict(r) -> Dict:
        d = dict(r)
        if d.get("text"):
            d["text"] = clean_boilerplate(d["text"])
        return d

    def _locate(self, para_id: str) -> Optional[Dict]:
        r = self.conn.execute(
            """SELECT para_id, paper_id, section_id, section_level1, section_level2,
                      section_level3, text, sequence, page
               FROM paragraphs WHERE para_id = ?""",
            (para_id,),
        ).fetchone()
        return self._row_dict(r) if r else None

    def _section_path(self, section_id: Optional[str], paper_id: str) -> List[str]:
        if not section_id:
            return []
        rows = self.conn.execute(
            """
            WITH RECURSIVE anc(section_id, parent_id, title, depth) AS (
                SELECT section_id, parent_id, title, 1
                FROM sections WHERE section_id = ?
                UNION ALL
                SELECT s.section_id, s.parent_id, s.title, anc.depth + 1
                FROM sections s JOIN anc ON s.section_id = anc.parent_id
            )
            SELECT title FROM anc ORDER BY depth DESC
            """,
            (section_id,),
        ).fetchall()
        return [row[0] for row in rows if row[0]]

    def _section_key(self, loc: Dict) -> tuple:
        if loc.get("section_id"):
            return (loc["paper_id"], "sec", loc["section_id"])
        if loc.get("section_level1"):
            return (loc["paper_id"], "l1", loc["section_level1"])
        if loc.get("section_level2"):
            return (loc["paper_id"], "l2", loc["section_level2"])
        return (loc["paper_id"], "solo", loc["para_id"])

    def _fetch_section(self, paper_id: str, kind: str, value: str) -> List[Dict]:
        if kind == "sec":
            rows = self.conn.execute(
                """SELECT para_id, paper_id, section_id, section_level1, section_level2,
                          section_level3, text, sequence, page
                   FROM paragraphs
                   WHERE paper_id = ? AND section_id = ?
                   ORDER BY sequence""",
                (paper_id, value),
            ).fetchall()
        else:
            col = "section_level1" if kind == "l1" else "section_level2"
            rows = self.conn.execute(
                f"""SELECT para_id, paper_id, section_id, section_level1, section_level2,
                           section_level3, text, sequence, page
                    FROM paragraphs
                    WHERE paper_id = ? AND {col} = ?
                    ORDER BY sequence""",
                (paper_id, value),
            ).fetchall()
        return [self._row_dict(r) for r in rows]

    def _fetch_window(self, loc: Dict, before: int, after: int) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT para_id, paper_id, section_id, section_level1, section_level2,
                      section_level3, text, sequence, page
               FROM paragraphs
               WHERE paper_id = ? AND sequence BETWEEN ? AND ?
               ORDER BY sequence""",
            (loc["paper_id"], loc["sequence"] - before, loc["sequence"] + after),
        ).fetchall()
        return [self._row_dict(r) for r in rows]

    def _fetch_sentences(self, para_id: str) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT sentence_id, text, sequence, page, bbox, char_start, char_end
               FROM sentences WHERE para_id = ? ORDER BY sequence""",
            (para_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _tokens(text: str) -> set:
        return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}

    def _pick_highlight(
        self, sentences: List[Dict], query: Optional[str]
    ) -> Optional[Dict]:
        """Best lexical-overlap sentence in the paragraph."""
        if not sentences:
            return None
        if not query:
            return sentences[0]
        if os.environ.get("SCIPAL_ANCHOR_ROLES") == "1":
            return pick_anchor(sentences, query) or sentences[0]
        q = self._tokens(query)
        if not q:
            return sentences[0]
        best = None
        best_score = 0
        for sentence in sentences:
            score = len(q & self._tokens(sentence.get("text", "")))
            if score > best_score:
                best, best_score = sentence, score
        return best or sentences[0]

    def expand(self, hits: List[Dict], mode: str = "section",
               max_parents: int = 4, max_section_paras: int = 12,
               window_before: int = 3, window_after: int = 3,
               query: Optional[str] = None) -> List[Dict]:
        """Expand ranked paragraph hits into parent context units."""
        groups: Dict[tuple, Dict] = {}
        for rank, hit in enumerate(hits):
            para_id = hit.get("para_id")
            if not para_id:
                continue
            loc = self._locate(para_id)
            if not loc:
                continue
            score = hit.get("rerank_score") or hit.get("score") or hit.get("rrf_score") or 0.0
            key = self._section_key(loc) if mode == "section" else \
                  (loc["paper_id"], "win", f"{loc['sequence']}")
            g = groups.setdefault(key, {
                "paper_id": loc["paper_id"], "hits": [], "best_score": -1e9,
                "best_loc": loc, "best_rank": rank,
            })
            g["hits"].append(loc)
            if score > g["best_score"]:
                g["best_score"] = score
                g["best_loc"] = loc
                g["best_rank"] = rank

        parents = []
        for key, g in groups.items():
            paper_id, kind, value = key
            hit_ids = {h["para_id"] for h in g["hits"]}
            best = g["best_loc"]

            paras: List[Dict] = []
            used_mode = mode
            if mode == "section":
                if kind in ("sec", "l1", "l2"):
                    paras = self._fetch_section(paper_id, kind, value)
                    if len(paras) > max_section_paras:
                        paras = self._fetch_window(best, window_before + 2, window_after + 2)
                        used_mode = "window(section-too-big)"
                else:
                    paras = self._fetch_window(best, window_before, window_after)
                    used_mode = "window(no-section)"
            else:
                paras = self._fetch_window(best, window_before, window_after)
                used_mode = "window"

            if not paras:
                continue

            text_parts, matched_seq, matched_sentences = [], [], []
            for p in paras:
                if p["para_id"] in hit_ids:
                    matched_seq.append(p["sequence"])
                    sentences = self._fetch_sentences(p["para_id"])
                    highlight = self._pick_highlight(sentences, query)
                    if highlight:
                        matched_sentences.append(highlight)
                        marked = self._mark_sentence(p["text"], highlight["text"])
                    else:
                        marked = f"{HIT_START} {p['text']} {HIT_END}"
                    text_parts.append(marked)
                else:
                    text_parts.append(p["text"])

            section_path = self._section_path(best.get("section_id"), paper_id)
            section = " › ".join(section_path) if section_path else (
                best.get("section_level1") or best.get("section_level2") or ""
            )
            parents.append({
                "parent_id": f"{paper_id}::{kind}::{value}",
                "paper_id": paper_id,
                "section_id": best.get("section_id"),
                "section": section,
                "section_path": section_path,
                "page": best.get("page"),
                "mode": used_mode,
                "matched_para_ids": sorted(hit_ids),
                "matched_sequences": sorted(matched_seq),
                "matched_sentences": matched_sentences,
                "score": g["best_score"],
                "n_paragraphs": len(paras),
                "paragraphs": paras,
                "text": "\n\n".join(text_parts),
            })

        parents.sort(key=lambda x: -x["score"])
        return parents[:max_parents]

    @staticmethod
    def _mark_sentence(paragraph: str, sentence: str) -> str:
        if sentence and sentence in paragraph:
            return paragraph.replace(
                sentence, f"{HIT_START}{sentence}{HIT_END}", 1
            )
        return f"{HIT_START} {paragraph} {HIT_END}"


if __name__ == "__main__":
    expander = ContextExpander()
    rows = expander.conn.execute(
        "SELECT para_id FROM paragraphs WHERE section_id IS NOT NULL LIMIT 3"
    ).fetchall()
    units = expander.expand([{"para_id": r[0], "score": 1.0} for r in rows])
    for unit in units:
        print(unit["section_path"], unit["mode"], len(unit["matched_sentences"]))
