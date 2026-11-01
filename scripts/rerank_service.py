#!/usr/bin/env python3
"""Warm local reranker HTTP service.

Start once, wait for /health, then reuse for benchmark or offline analysis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Handler(BaseHTTPRequestHandler):
    model = None
    model_name = ""

    def log_message(self, fmt: str, *args) -> None:
        print(f"[rerank] {fmt % args}", file=sys.stderr, flush=True)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "model": self.model_name})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/score":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            query = str(data["query"])
            texts = [str(text) for text in data["texts"]]
            batch_size = int(data.get("batch_size", 8))
            if self.model is None:
                raise RuntimeError("model is not ready")
            scores = self.model.predict(
                [(query, text) for text in texts],
                batch_size=batch_size,
            )
            self._json(200, {"scores": [float(score) for score in scores]})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc)[:500]})

    @classmethod
    def configure(cls, model, model_name: str) -> None:
        cls.model = model
        cls.model_name = model_name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default=os.environ.get("SCIPAL_RERANK_MODEL", ""))
    args = parser.parse_args()

    import torch

    torch.set_num_threads(1)
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(args.model)
    Handler.configure(model, args.model)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"READY http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
