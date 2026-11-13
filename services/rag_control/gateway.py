"""R5: minimal RAG gateway. Only code_search is routed for now."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from services.db.pg_pool import core_connection
from services.rag_control.ledger import append_evidence
from services.rag_control.models import list_bindings
from services.rag_control.registry import get_provider


class GatewayError(ValueError):
    pass


def _run(rag_id: str, library_id: str, snapshot: str, model_version: str, metadata: dict[str, Any]) -> str:
    run_id = "qry_" + uuid.uuid4().hex[:12]
    pg = core_connection()
    try:
        pg.execute(
            """
            INSERT INTO rag_runs
              (run_id,job_id,rag_id,library_id,snapshot,model_version,exit_code,metrics,run_type,started_at,finished_at)
            VALUES (%s,NULL,%s,%s,%s,%s,0,%s::jsonb,'query',now(),now())
            """,
            (run_id, rag_id, library_id, snapshot, model_version, json.dumps(metadata, ensure_ascii=False)),
        )
        pg.commit()
        return run_id
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def query(*, capability: str, library_id: str, query_text: str, top_k: int = 10, timeout: int = 30) -> dict[str, Any]:
    capability = (capability or "").strip()
    if capability != "code_search":
        raise GatewayError(f"unsupported capability: {capability}")
    if not library_id or not (query_text or "").strip():
        raise GatewayError("library_id and query are required")
    provider = get_provider("code")
    if not provider:
        raise GatewayError("code provider not registered")
    endpoint = str(provider.get("endpoint") or "").rstrip("/")
    if not endpoint.startswith("http"):
        raise GatewayError("code provider endpoint is not HTTP")
    body = json.dumps(
        {"query": query_text, "top_k": max(1, min(int(top_k), 50))}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint + f"/libraries/{urllib.parse.quote(library_id)}/search",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GatewayError(f"code RAG rejected query: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GatewayError(f"code RAG unavailable: {exc}") from exc
    hits = payload.get("hits") or []
    snapshot = str(hits[0].get("snapshot_id") or "") if hits else ""
    model_version = ""
    bindings = list_bindings(rag_id="code", library_id=library_id)
    if bindings:
        model_version = str(bindings[0].get("embedding_model") or "")
    run_id = _run(
        "code",
        library_id,
        snapshot,
        model_version,
        {"capability": capability, "query": query_text, "hits": len(hits)},
    )
    results = []
    for hit in hits:
        snippet = str(hit.get("snippet") or "")
        evidence = append_evidence(
            run_id,
            {
                "rag_id": "code",
                "library_id": library_id,
                "snapshot": str(hit.get("snapshot_id") or snapshot),
                "source_path": str(hit.get("path") or ""),
                "start_line": hit.get("start_line"),
                "end_line": hit.get("end_line"),
                "content_hash": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                "model_version": model_version,
                "score": hit.get("score"),
                "metadata": {
                    "unit_id": hit.get("unit_id"),
                    "symbol_name": hit.get("symbol_name"),
                    "unit_type": hit.get("unit_type"),
                },
            },
        )
        item = dict(hit)
        item["evidence_id"] = evidence["evidence_id"]
        results.append(item)
    return {
        "run_id": run_id,
        "rag_id": "code",
        "library_id": library_id,
        "query": query_text,
        "results": results,
    }
