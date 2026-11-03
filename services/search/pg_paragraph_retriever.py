"""PostgreSQL paragraph FTS candidate recall + cross-encoder rerank."""

from __future__ import annotations

import logging
import os
from typing import Optional

from services.search.pg_fts import PGParagraphFTS

LOGGER = logging.getLogger(__name__)


class PGParagraphRetriever:
    def __init__(self, dsn: Optional[str] = None, *, reranker=None):
        self.dsn = dsn or os.environ.get("SCIPAL_PG_DSN", "")
        self.fts = PGParagraphFTS(self.dsn, ranker="rank")
        self._reranker = reranker

    @property
    def reranker(self):
        if self._reranker is None:
            from services.search.reranker import Reranker

            self._reranker = Reranker()
        return self._reranker

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        paper_id: str = "",
        section_l1: str = "",
    ) -> list[dict]:
        candidates = self.fts.search(
            query,
            top_k=int(os.environ.get("SCIPAL_PG_FTS_CANDIDATES", "50")),
            paper_id=paper_id,
            section_level1=section_l1,
            term_limit=int(os.environ.get("SCIPAL_PG_FTS_TERM_LIMIT", "3")),
        )
        if not candidates:
            return []
        reranked = self.reranker.rerank(
            query,
            [{"para_id": hit.para_id, "text": hit.text} for hit in candidates],
            top_k=top_k,
        )
        by_id = {hit.para_id: hit for hit in candidates}
        out = []
        for row in reranked:
            hit = by_id.get(row["para_id"])
            if hit is None:
                continue
            out.append(
                {
                    "para_id": hit.para_id,
                    "paper_id": hit.paper_id,
                    "section_l1": hit.section_level1,
                    "section_l2": hit.section_level2,
                    "text": hit.text,
                    "score": float(row.get("rerank_score", 0.0)),
                }
            )
        return out
