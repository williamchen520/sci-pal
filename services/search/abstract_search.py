"""Abstract search compatibility stub.

The abstract vector/FTS store was retired with the Chroma/SQLite backends.
Production uses PostgreSQL full-text/vector retrieval for the main library;
this class remains only as a no-op channel for UnifiedRetriever callers.
"""

from __future__ import annotations

from typing import Dict, List


class AbstractSearch:
    def __init__(self) -> None:
        pass

    def vector_search(self, query: str, top_k: int = 10) -> List[Dict]:
        return []

    def fts_search(self, query: str, top_k: int = 10) -> List[Dict]:
        return []

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        return []
