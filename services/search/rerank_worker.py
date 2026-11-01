"""Isolated reranker worker with per-request timeout and in-memory cache.

The worker loads the cross-encoder in a child process. The parent never shares a
PyTorch process with FTS/database work, so a slow or wedged inference cannot
block the experiment loop. A timed-out worker is terminated and restarted.
"""

from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
from typing import Iterable, List, Optional


def _worker_main(conn, model_name: str) -> None:
    try:
        import torch

        torch.set_num_threads(1)
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(model_name)
        conn.send(("ready", None))
        while True:
            job = conn.recv()
            if job is None:
                break
            query, texts, batch_size = job
            scores = model.predict(
                [(query, text) for text in texts],
                batch_size=batch_size,
            )
            conn.send(("scores", [float(score) for score in scores]))
    except Exception as exc:  # noqa: BLE001
        try:
            conn.send(("error", str(exc)[:500]))
        except Exception:  # noqa: BLE001
            pass
    finally:
        conn.close()


class RerankWorker:
    def __init__(self, model_name: Optional[str] = None, *, timeout: float = 30.0):
        self.model_name = model_name or os.environ.get("SCIPAL_RERANK_MODEL", "")
        self.timeout = timeout
        self._cache: dict[str, List[float]] = {}
        self._ctx = mp.get_context("spawn")
        self._conn = None
        self._proc = None
        self._start()

    def _start(self) -> None:
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=_worker_main,
            args=(child, self.model_name),
            daemon=True,
        )
        proc.start()
        child.close()
        if not parent.poll(self.timeout):
            proc.terminate()
            raise TimeoutError("reranker worker did not become ready")
        status, payload = parent.recv()
        if status != "ready":
            proc.terminate()
            raise RuntimeError(f"reranker worker failed: {payload}")
        self._conn, self._proc = parent, proc

    def _stop(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
            except Exception:  # noqa: BLE001
                pass
            self._conn.close()
        if self._proc is not None:
            self._proc.join(timeout=2)
            if self._proc.is_alive():
                self._proc.terminate()
        self._conn = None
        self._proc = None

    def _restart(self) -> None:
        self._stop()
        self._start()

    @staticmethod
    def _key(query: str, texts: Iterable[str], batch_size: int) -> str:
        digest = hashlib.sha256()
        digest.update(query.encode("utf-8"))
        for text in texts:
            digest.update(b"\0")
            digest.update(text.encode("utf-8"))
        digest.update(f"\0{batch_size}".encode("ascii"))
        return digest.hexdigest()

    def score(
        self,
        query: str,
        texts: List[str],
        *,
        batch_size: int = 8,
        timeout: Optional[float] = None,
    ) -> List[float]:
        texts = list(texts)
        if not texts:
            return []
        key = self._key(query, texts, batch_size)
        if key in self._cache:
            return list(self._cache[key])
        if self._conn is None:
            self._start()
        self._conn.send((query, texts, batch_size))
        wait = self.timeout if timeout is None else timeout
        if not self._conn.poll(wait):
            self._restart()
            raise TimeoutError(f"reranker timed out after {wait:.1f}s")
        status, payload = self._conn.recv()
        if status != "scores":
            self._restart()
            raise RuntimeError(f"reranker failed: {payload}")
        self._cache[key] = list(payload)
        return list(payload)

    def close(self) -> None:
        self._stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
