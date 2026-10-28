"""Vector retrieval over section summaries (Chroma)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import chromadb

DEFAULT_CHROMA = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
MODEL = os.environ.get(
    "SCIPAL_EMBEDDING_MODEL", r"D:\models\models\BAAI--bge-base-en-v1.5"
)


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
