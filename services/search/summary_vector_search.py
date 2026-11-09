"""Summary vector search compatibility stub.

Chroma/section-summary vector retrieval was retired with the PG-only migration.
Keep the class for call-site compatibility; it is a no-op now.
"""

from __future__ import annotations

from typing import Dict, List


class SummaryVectorSearch:
    def __init__(self, chroma_path=None) -> None:
        self.chroma_path = chroma_path

    def available(self) -> bool:
        return False

    def search(self, query: str, top_k: int = 3, paper_id: str = "") -> List[Dict]:
        return []

    def expand(
        self,
        query: str,
        hits: List[Dict],
        top_sentences: int = 2,
        max_distance: float = 0.35,
    ) -> List[Dict]:
        return []


_DEFAULT = None


def get_default() -> "SummaryVectorSearch":
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SummaryVectorSearch()
    return _DEFAULT
