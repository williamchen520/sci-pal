"""HTTP client for the warm reranker service."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Iterable, List


class RerankClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, List[float]] = {}

    @staticmethod
    def _key(query: str, texts: Iterable[str], batch_size: int) -> str:
        digest = hashlib.sha256()
        digest.update(query.encode("utf-8"))
        for text in texts:
            digest.update(b"\0")
            digest.update(text.encode("utf-8"))
        digest.update(f"\0{batch_size}".encode("ascii"))
        return digest.hexdigest()

    def health(self, timeout: float = 5.0) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + "/health", timeout=timeout) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def score(
        self,
        query: str,
        texts: List[str],
        *,
        batch_size: int = 8,
        timeout: float | None = None,
    ) -> List[float]:
        texts = list(texts)
        if not texts:
            return []
        key = self._key(query, texts, batch_size)
        if key in self._cache:
            return list(self._cache[key])
        payload = json.dumps(
            {"query": query, "texts": texts, "batch_size": batch_size},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/score",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        wait = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=wait) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise TimeoutError(f"reranker request timed out after {wait:.1f}s") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"reranker service unavailable: {exc}") from exc
        scores = [float(value) for value in body.get("scores", [])]
        if len(scores) != len(texts):
            raise RuntimeError("reranker returned a mismatched score count")
        self._cache[key] = scores
        return list(scores)

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
