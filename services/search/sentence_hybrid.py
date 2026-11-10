"""Sentence-hybrid retrieval prototype.

Paragraph vectors provide a semantic prior; sentence lexical search provides
the actual ranking unit. Context is attached after ranking and is never scored.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional

from config.paths import EMBEDDING_MODEL
from services.search.pg_vector import PGVectorParagraphSearch
from services.search.reranker import Reranker
from services.search.sentence_window import WindowPolicy, build_context

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _ts_query(query: str) -> str:
    terms = [term for term in TOKEN_RE.findall(query or "") if len(term) > 1]
    return " | ".join(terms)


class SentenceHybridRetriever:
    def __init__(
        self,
        *,
        model=None,
        vector: Optional[PGVectorParagraphSearch] = None,
        reranker=None,
        paragraph_top_k: int = 50,
        sentence_top_k: int = 200,
        rerank_pool: int = 50,
        lexical_weight: float = 0.7,
        paragraph_weight: float = 0.3,
        context_policy: Optional[WindowPolicy] = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = model or SentenceTransformer(
            os.environ.get("SCIPAL_EMBEDDING_MODEL", EMBEDDING_MODEL)
        )
        self.vector = vector or PGVectorParagraphSearch()
        self.reranker = reranker or Reranker()
        self.paragraph_top_k = paragraph_top_k
        self.sentence_top_k = sentence_top_k
        self.rerank_pool = rerank_pool
        self.lexical_weight = lexical_weight
        self.paragraph_weight = paragraph_weight
        self.context_policy = context_policy or WindowPolicy.from_config()

    def _pg(self):
        from services.db.pg_pool import corpus_connection

        return corpus_connection()

    @staticmethod
    def _lexical_rows(pg, query: str, limit: int) -> List[Dict[str, Any]]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        rows = pg.execute(
            "SELECT sentence_id, para_id, paper_id, text, sequence, "
            "ts_rank(search_vector, to_tsquery('english', %s)) AS rank "
            "FROM sentences WHERE search_vector @@ to_tsquery('english', %s) "
            "ORDER BY rank DESC, sentence_id LIMIT %s",
            (ts_query, ts_query, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _sentences_for_paragraphs(
        pg, para_ids: Iterable[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        ids = list(dict.fromkeys(pid for pid in para_ids if pid))
        if not ids:
            return {}
        rows = pg.execute(
            "SELECT sentence_id, para_id, paper_id, section_id, text, sequence "
            "FROM sentences WHERE para_id = ANY(%s) ORDER BY para_id, sequence",
            (ids,),
        ).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["para_id"], []).append(dict(row))
        return grouped

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        query_vec = self.model.encode([query], normalize_embeddings=True)[0]
        paragraph_hits = self.vector.search(query_vec, top_k=self.paragraph_top_k)
        paragraph_rank = {
            hit.para_id: index for index, hit in enumerate(paragraph_hits)
        }

        pg = self._pg()
        try:
            lexical = self._lexical_rows(pg, query, self.sentence_top_k)
            by_paragraph = self._sentences_for_paragraphs(
                pg, [hit.para_id for hit in paragraph_hits]
            )
        finally:
            pg.close()

        lexical_rank = {
            row["sentence_id"]: index for index, row in enumerate(lexical, start=1)
        }

        candidates: Dict[str, Dict[str, Any]] = {}
        for row in lexical:
            candidates[row["sentence_id"]] = dict(row)
        for rows in by_paragraph.values():
            for row in rows:
                candidates.setdefault(row["sentence_id"], dict(row))

        scored = []
        for sentence_id, row in candidates.items():
            lex = self.lexical_weight / (60 + lexical_rank[sentence_id]) if sentence_id in lexical_rank else 0.0
            prior_rank = paragraph_rank.get(row["para_id"])
            prior = self.paragraph_weight / (60 + prior_rank) if prior_rank is not None else 0.0
            scored.append((lex + prior, row, lex, prior, prior_rank))
        scored.sort(key=lambda item: (-item[0], item[1]["sentence_id"]))

        # Keep a few sentences from each top paragraph in the rerank pool.
        # Without this, a paragraph whose sentences do not match lexically is
        # represented only by its prior and is cut before the cross-encoder.
        meta_by_id = {row["sentence_id"]: (score, row, lex, prior, prior_rank) for score, row, lex, prior, prior_rank in scored}
        pool = []
        chosen = set()
        for hit in paragraph_hits[:15]:
            rows = sorted(by_paragraph.get(hit.para_id, []), key=lambda row: row.get("sequence") or 0)
            if not rows:
                continue
            picks = rows[:3]
            lexical_rows = [row for row in rows if row["sentence_id"] in lexical_rank]
            if lexical_rows:
                best = min(lexical_rows, key=lambda row: lexical_rank[row["sentence_id"]])
                if best not in picks:
                    picks[-1] = best
            for row in picks:
                if row["sentence_id"] not in chosen:
                    pool.append(meta_by_id[row["sentence_id"]])
                    chosen.add(row["sentence_id"])
        for item in scored:
            if len(pool) >= self.rerank_pool:
                break
            row = item[1]
            if row["sentence_id"] not in chosen:
                pool.append(item)
                chosen.add(row["sentence_id"])
        pool = pool[: self.rerank_pool]
        reranked = self.reranker.rerank(
            query,
            [
                {
                    "sentence_id": row["sentence_id"],
                    "text": (row.get("text") or "")[:800],
                }
                for _, row, _, _, _ in pool
            ],
            top_k=top_k,
            batch_size=16,
        )
        by_id = {row["sentence_id"]: (score, row, lex, prior, prior_rank) for score, row, lex, prior, prior_rank in pool}

        anchors = []
        for hit in reranked:
            score, row, lex, prior, prior_rank = by_id[hit["sentence_id"]]
            anchors.append(
                {
                    "sentence_id": row["sentence_id"],
                    "para_id": row["para_id"],
                    "paper_id": row["paper_id"],
                    "text": row.get("text") or "",
                    "score": hit.get("rerank_score"),
                    "lexical_rank": lexical_rank.get(row["sentence_id"]),
                    "paragraph_rank": prior_rank,
                    "lexical_score": lex,
                    "paragraph_prior": prior,
                }
            )

        pg = self._pg()
        try:
            context_rows = self._sentences_for_paragraphs(
                pg, [anchor["para_id"] for anchor in anchors]
            )
        finally:
            pg.close()

        units = []
        for anchor in anchors:
            unit = build_context(
                anchor,
                context_rows.get(anchor["para_id"], []),
                query=query,
                policy=self.context_policy,
            )
            units.append(unit.as_dict())
        return units


    def to_evidence_json(self, query: str, paper_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Return the same bundle shape as UnifiedRetriever.to_evidence_json.

        The anchor sentence is the ranked unit; the logical window is attached
        as context and is never scored.
        """
        top_k = int(kwargs.get("top_paragraphs") or kwargs.get("top_k") or 10)
        units = self.search(query, top_k=top_k)
        if paper_id:
            units = [unit for unit in units if unit.get("paper_id") == paper_id]
        evidence = []
        for unit in units:
            sentence_id = unit.get("sentence_id")
            anchor_text = unit.get("anchor_text") or ""
            evidence.append(
                {
                    "paper_id": unit.get("paper_id"),
                    "para_id": unit.get("para_id"),
                    "section_path": [],
                    "text": unit.get("text") or anchor_text,
                    "highlight": [
                        {
                            "sentence_id": sentence_id,
                            "text": anchor_text,
                            "score": unit.get("anchor_score"),
                        }
                    ],
                    "matched_sentences": [
                        {"sentence_id": sentence_id, "text": anchor_text}
                    ],
                    "paragraph_details": [
                        {
                            "para_id": unit.get("para_id"),
                            "sentence_ids": [
                                row.get("sentence_id")
                                for row in unit.get("window_sentences") or []
                                if row.get("sentence_id")
                            ],
                            "text": unit.get("paragraph_text") or "",
                        }
                    ],
                }
            )
        return {
            "query": query,
            "evidence": evidence,
            "sufficient": bool(evidence),
            "sufficiency": {"sufficient": bool(evidence), "reason": "sentence_backend"},
            "summaries": [],
        }
