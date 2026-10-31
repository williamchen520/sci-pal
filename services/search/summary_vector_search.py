"""Vector retrieval over section summaries (Chroma)."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import chromadb

DEFAULT_CHROMA = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"
from config.paths import EMBEDDING_MODEL as MODEL


class SummaryVectorSearch:
    def __init__(self, chroma_path: Path | str = DEFAULT_CHROMA):
        self.chroma_path = str(chroma_path)
        self._model = None
        self._collection = None

    def available(self) -> bool:
        try:
            client = chromadb.PersistentClient(path=self.chroma_path)
            client.get_collection("section_summaries")
            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure(self) -> bool:
        if self._model is not None and self._collection is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            client = chromadb.PersistentClient(path=self.chroma_path)
            self._collection = client.get_collection("section_summaries")
            self._model = SentenceTransformer(MODEL)
            return True
        except Exception:  # noqa: BLE001
            return False

    def search(self, query: str, top_k: int = 3, paper_id: str = "") -> List[Dict]:
        if not self._ensure():
            return []
        embedding = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0].tolist()
        where = {"paper_id": paper_id} if paper_id else None
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        out: List[Dict] = []
        for index, summary_id in enumerate((result.get("ids") or [[]])[0]):
            metadata = (result.get("metadatas") or [[]])[0][index] or {}
            out.append(
                {
                    "summary_id": summary_id,
                    "paper_id": metadata.get("paper_id"),
                    "section_id": metadata.get("section_id"),
                    "title": metadata.get("title"),
                    "text": (result.get("documents") or [[]])[0][index],
                    "distance": round((result.get("distances") or [[0]])[0][index], 4),
                }
            )
        return out

    def expand(
        self,
        query: str,
        hits: List[Dict],
        top_sentences: int = 2,
        max_distance: float = 0.35,
    ) -> List[Dict]:
        """Map vector summary hits back to their best-matching sentences."""
        query_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", query)
            if len(token) > 2
        }
        if not query_tokens:
            return []
        conn = sqlite3.connect(str(DEFAULT_DB))
        conn.row_factory = sqlite3.Row
        contexts: List[Dict] = []
        try:
            for hit in hits:
                if (hit.get("distance") or 1.0) > max_distance:
                    continue
                rows = conn.execute(
                    "SELECT sentence_id, text, page FROM sentences "
                    "WHERE section_id = ? AND length(text) BETWEEN 40 AND 400 "
                    "ORDER BY sequence LIMIT 60",
                    (hit.get("section_id"),),
                ).fetchall()
                scored = []
                for row in rows:
                    tokens = {
                        token.lower()
                        for token in re.findall(r"[A-Za-z0-9]+", row["text"])
                        if len(token) > 2
                    }
                    score = len(query_tokens & tokens) / len(query_tokens)
                    if score > 0:
                        scored.append((score, row))
                if not scored:
                    continue
                scored.sort(key=lambda item: item[0], reverse=True)
                picked = scored[:top_sentences]
                contexts.append(
                    {
                        "paper_id": hit.get("paper_id"),
                        "section_id": hit.get("section_id"),
                        "section": hit.get("title") or "",
                        "section_path": [hit.get("title") or ""],
                        "page": picked[0][1]["page"],
                        "score": round(1 - (hit.get("distance") or 1.0), 4),
                        "text": " ".join(item[1]["text"] for item in picked),
                        "paragraphs": [{"text": item[1]["text"]} for item in picked],
                        "matched_sentences": [
                            {
                                "sentence_id": item[1]["sentence_id"],
                                "text": item[1]["text"],
                                "page": item[1]["page"],
                            }
                            for item in picked
                        ],
                    }
                )
        finally:
            conn.close()
        return contexts


_DEFAULT = None


def get_default() -> "SummaryVectorSearch":
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SummaryVectorSearch()
    return _DEFAULT