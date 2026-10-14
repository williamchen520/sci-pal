"""
Small-to-big (parent document) retrieval.
V21.5 - Small-to-big context expansion

Retrieval stays precise at the paragraph (small chunk) level, but the LLM is
handed the surrounding parent context (the whole section, or a bounded window
when the section is too large). This fixes "tiny chunk lacks context" without
blunting retrieval precision.

Two expansion modes:
  - "section": group hits by (paper_id, section_level1) and return the whole
               section in reading order; the matched paragraph(s) are marked.
               If a section exceeds max_section_paras, fall back to a window
               centred on the best hit.
  - "window":  a fixed number of paragraphs before/after each hit.

Overlapping parents are merged; a parent's score is the max score of the hits
inside it.
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional

from services.search.boilerplate_filter import clean_boilerplate

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# Markers wrap the matched paragraph inside the expanded text, so the LLM (and
# the UI) can see which sentence actually answered vs. surrounding context.
HIT_START = "►"
HIT_END = "◄"


class ContextExpander:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def _row_dict(r) -> Dict:
        """Convert a DB row to dict, stripping front-matter boilerplate lines."""
        d = dict(r)
        if d.get("text"):
            d["text"] = clean_boilerplate(d["text"])
        return d

    def _locate(self, para_id: str) -> Optional[Dict]:
        """Look up a paragraph's location fields from its id (source of truth)."""
        r = self.conn.execute(
            """SELECT para_id, paper_id, section_level1, section_level2,
                      section_level3, text, sequence, page
               FROM paragraphs WHERE para_id = ?""",
            (para_id,),
        ).fetchone()
        if not r:
            return None
        return self._row_dict(r)

    def _section_key(self, loc: Dict) -> tuple:
        """Parent grouping key; fall back through section levels."""
        if loc.get("section_level1"):
            return (loc["paper_id"], "l1", loc["section_level1"])
        if loc.get("section_level2"):
            return (loc["paper_id"], "l2", loc["section_level2"])
        # No section info: treat a tight window around the hit as the parent.
        return (loc["paper_id"], "solo", loc["para_id"])

    def _fetch_section(self, paper_id: str, level: str, value: str) -> List[Dict]:
        col = "section_level1" if level == "l1" else "section_level2"
        rows = self.conn.execute(
            f"""SELECT para_id, paper_id, section_level1, section_level2,
                       section_level3, text, sequence, page
                FROM paragraphs
                WHERE paper_id = ? AND {col} = ?
                ORDER BY sequence""",
            (paper_id, value),
        ).fetchall()
        return [self._row_dict(r) for r in rows]

    def _fetch_window(self, loc: Dict, before: int, after: int) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT para_id, paper_id, section_level1, section_level2,
                      section_level3, text, sequence, page
               FROM paragraphs
               WHERE paper_id = ? AND sequence BETWEEN ? AND ?
               ORDER BY sequence""",
            (loc["paper_id"], loc["sequence"] - before, loc["sequence"] + after),
        ).fetchall()
        return [self._row_dict(r) for r in rows]

    def expand(self, hits: List[Dict], mode: str = "section",
               max_parents: int = 4, max_section_paras: int = 12,
               window_before: int = 3, window_after: int = 3) -> List[Dict]:
        """
        Expand ranked paragraph hits into parent context units.

        Args:
            hits: list of hit dicts, each must contain 'para_id' and optionally
                  a 'score' / 'rerank_score' / 'rrf_score'.
        Returns:
            list of parent units:
              {parent_id, paper_id, section, mode, matched_para_ids,
               matched_sequences, score, paragraphs:[...], text}
            sorted by best-hit score desc, capped at max_parents.
        """
        # 1. Locate every hit and collect into parent groups.
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

        # 2. Materialise each parent (whole section or window).
        parents = []
        for key, g in groups.items():
            paper_id, kind, value = key
            hit_ids = {h["para_id"] for h in g["hits"]}
            best = g["best_loc"]

            paras: List[Dict] = []
            used_mode = mode
            if mode == "section":
                if kind in ("l1", "l2"):
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

            # Build the joined text, marking matched paragraphs.
            text_parts, matched_seq = [], []
            for p in paras:
                if p["para_id"] in hit_ids:
                    matched_seq.append(p["sequence"])
                    text_parts.append(f"{HIT_START} {p['text']} {HIT_END}")
                else:
                    text_parts.append(p["text"])

            section = best.get("section_level1") or best.get("section_level2") or ""
            parents.append({
                "parent_id": f"{paper_id}::{key[1]}::{value}",
                "paper_id": paper_id,
                "section": section,
                "page": best.get("page"),
                "mode": used_mode,
                "matched_para_ids": sorted(hit_ids),
                "matched_sequences": sorted(matched_seq),
                "score": g["best_score"],
                "n_paragraphs": len(paras),
                "paragraphs": paras,
                "text": "\n\n".join(text_parts),
            })

        # 3. Rank by best hit, cap. (Tie-break: earlier rank.)
        parents.sort(key=lambda x: -x["score"])
        return parents[:max_parents]


if __name__ == "__main__":
    from services.search.hybrid_search import HybridSearch
    from services.search.reranker import Reranker

    print("=" * 60)
    print("🔎 Small-to-Big Expansion Test")
    print("=" * 60)

    searcher = HybridSearch()
    reranker = Reranker()
    expander = ContextExpander()

    query = "How does STAT1 regulate the interferon response?"
    print(f"\nQuery: {query}\n")

    # Precise paragraph-level recall + rerank (the "small")
    vector = searcher.vector_search(query, 20)
    fts = searcher.fts_search(query, 20)
    fused = searcher.rrf_fuse(vector, fts, 20)
    top_hits = reranker.rerank(query, fused, 6)

    print(f"Precise hits: {len(top_hits)} paragraphs")
    parents = expander.expand(top_hits, mode="section", max_parents=3)
    print(f"Expanded to {len(parents)} parent sections:\n")

    for i, p in enumerate(parents):
        marked = len(p["matched_sequences"])
        print(f"  [Parent {i+1}] score={p['score']:.3f} mode={p['mode']} "
              f"section='{p['section'][:40]}' paras={p['n_paragraphs']} "
              f"hits={marked}")
        preview = p["text"][:220].replace("\n", " ")
        print(f"      {preview}...\n")
