#!/usr/bin/env python3
"""R3 local RAG worker: lease, execute code_ingest, register binding, complete."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

API_BASE = os.environ.get("SCIPAL_API_BASE", "http://127.0.0.1:5001").rstrip("/")
TOKEN = os.environ.get("SCIPAL_RAG_WORKER_TOKEN", "").strip()
REPO_ROOT = Path(os.environ.get("SCIPAL_RAG_REPO_ROOT", r"G:/repos")).resolve()
EMBED_MODEL = os.environ.get("SCIPAL_RAG_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
DIMENSION = int(os.environ.get("SCIPAL_RAG_EMBED_DIM", "512"))
ARTIFACT_ROOT = Path(os.environ.get("SCIPAL_RAG_ARTIFACT_ROOT", r"G:/runs/rag_artifacts")).resolve()
CODE_API_BASE = os.environ.get("SCIPAL_CODE_API_URL", "http://127.0.0.1:5010").rstrip("/")
DOCS_API_BASE = os.environ.get("SCIPAL_DOCS_API_URL", "http://127.0.0.1:5011").rstrip("/")


def _headers() -> dict[str, str]:
    return {"X-SCIPAL-RAG-Worker-Token": TOKEN, "Content-Type": "application/json"}


def _post(path: str, body: dict) -> dict:
    response = requests.post(API_BASE + path, json=body, headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def _safe_repo(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise ValueError(f"repo outside allowlist: {REPO_ROOT}")
    return path


def _command(params: dict) -> list[str]:
    repo = _safe_repo(str(params.get("repo_path") or ""))
    language = str(params.get("language") or "python")
    if language not in {"python", "nextflow"}:
        raise ValueError(f"invalid language: {language}")
    command = [
        sys.executable,
        "-m",
        "code_rag.ingest",
        "--repo",
        str(repo),
        "--library-id",
        str(params.get("library_id") or ""),
        "--repo-url",
        str(params.get("repo_url") or ""),
        "--ref",
        str(params.get("ref") or ""),
        "--language",
        language,
    ]
    limit = int(params.get("limit") or 0)
    if limit:
        command += ["--limit", str(limit)]
    return command


def _write_manifest(job: dict, run_id: str, params: dict, snapshot: str, seconds: float) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / f"run_{run_id}.json"
    manifest = {
        "run_id": run_id,
        "job_id": job["job_id"],
        "plan_id": job["plan_id"],
        "rag_id": job["rag_id"],
        "library_id": job["library_id"],
        "snapshot": snapshot,
        "repo_path": params.get("repo_path"),
        "repo_url": params.get("repo_url"),
        "ref": params.get("ref"),
        "exit_code": 0,
        "seconds": round(seconds, 2),
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    raw = path.read_bytes()
    _post(
        f"/api/rag/runs/{run_id}/artifacts",
        {
            "kind": "run_manifest",
            "uri": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "license": "internal",
            "metadata": {"job_id": job["job_id"], "snapshot": snapshot},
        },
    )


def _heartbeat(job_id: str, worker_id: str, seconds: int, stop: threading.Event) -> None:
    while not stop.wait(seconds):
        try:
            _post(f"/api/rag/jobs/{job_id}/heartbeat", {"worker_id": worker_id, "lease_seconds": 120})
        except Exception:
            return


def _execute_literature_query(job: dict, worker_id: str) -> None:
    job_id = job["job_id"]
    payload = job.get("payload") or {}
    query_text = str(payload.get("query") or "")
    if not query_text:
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": "query required"})
        return
    started = time.time()
    try:
        response = requests.post(
            API_BASE + "/api/evidence/search",
            json={"query": query_text, "top_k": max(1, min(int((payload.get("params") or {}).get("top_k") or 10), 50))},
            headers=_headers(),
            timeout=90,
        )
        response.raise_for_status()
        entries = response.json().get("evidence") or []
    except Exception as exc:  # noqa: BLE001
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": str(exc)[:2000]})
        return
    evidence = []
    for entry in entries:
        matched = entry.get("matched_sentences") or []
        text = " ".join(str(item.get("text") or "") for item in matched)
        highlights = entry.get("highlight") or []
        evidence.append(
            {
                "rag_id": "literature",
                "library_id": "",
                "snapshot": "",
                "source_path": f"literature/{entry.get('paper_id')}/{entry.get('para_id')}",
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "model_version": "BAAI/bge-base-en-v1.5",
                "score": highlights[0].get("score") if highlights else None,
                "metadata": {
                    "paper_id": entry.get("paper_id"),
                    "para_id": entry.get("para_id"),
                    "sentence_ids": [item.get("sentence_id") for item in matched],
                },
            }
        )
    _post(
        f"/api/rag/jobs/{job_id}/complete",
        {
            "worker_id": worker_id,
            "snapshot": "",
            "model_version": "BAAI/bge-base-en-v1.5",
            "exit_code": 0,
            "metrics": {"hits": len(entries), "seconds": round(time.time() - started, 2)},
            "evidence": evidence,
        },
    )


def _execute_docs_query(job: dict, worker_id: str) -> None:
    job_id = job["job_id"]
    payload = job.get("payload") or {}
    query_text = str(payload.get("query") or "")
    if not query_text:
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": "query required"})
        return
    started = time.time()
    try:
        response = requests.post(
            DOCS_API_BASE + "/search",
            json={"query": query_text, "top_k": max(1, min(int((payload.get("params") or {}).get("top_k") or 8), 50)), "mode": "hybrid"},
            timeout=90,
        )
        response.raise_for_status()
        hits = response.json().get("hits") or []
    except Exception as exc:  # noqa: BLE001
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": str(exc)[:2000]})
        return
    evidence = []
    for hit in hits:
        text = str(hit.get("text") or "")
        evidence.append(
            {
                "rag_id": "docs",
                "library_id": "",
                "snapshot": "",
                "source_path": str(hit.get("path") or ""),
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "model_version": "BAAI/bge-small-zh-v1.5",
                "score": hit.get("score"),
                "metadata": {
                    "doc_id": hit.get("doc_id"),
                    "title": hit.get("title"),
                    "heading": hit.get("heading"),
                    "category": hit.get("category"),
                },
            }
        )
    _post(
        f"/api/rag/jobs/{job_id}/complete",
        {
            "worker_id": worker_id,
            "snapshot": "",
            "model_version": "BAAI/bge-small-zh-v1.5",
            "exit_code": 0,
            "metrics": {"hits": len(hits), "seconds": round(time.time() - started, 2)},
            "evidence": evidence,
        },
    )


def _execute_query(job: dict, worker_id: str) -> None:
    if job.get("rag_id") == "literature":
        _execute_literature_query(job, worker_id)
        return
    if job.get("rag_id") == "docs":
        _execute_docs_query(job, worker_id)
        return
    job_id = job["job_id"]
    payload = job.get("payload") or {}
    params = payload.get("params") or {}
    query_text = str(payload.get("query") or "")
    library_id = str(job.get("library_id") or params.get("library_id") or "")
    if not query_text or not library_id:
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": "query/library_id required"})
        return
    started = time.time()
    try:
        response = requests.post(
            f"{CODE_API_BASE}/libraries/{library_id}/search",
            json={"query": query_text, "top_k": max(1, min(int(params.get("top_k") or 10), 50))},
            timeout=60,
        )
        response.raise_for_status()
        hits = response.json().get("hits") or []
    except Exception as exc:  # noqa: BLE001
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": str(exc)[:2000]})
        return
    evidence = []
    snapshot = ""
    for hit in hits:
        snapshot = snapshot or str(hit.get("snapshot_id") or "")
        snippet = str(hit.get("snippet") or "")
        evidence.append(
            {
                "rag_id": "code",
                "library_id": library_id,
                "snapshot": str(hit.get("snapshot_id") or ""),
                "source_path": str(hit.get("path") or ""),
                "start_line": hit.get("start_line"),
                "end_line": hit.get("end_line"),
                "content_hash": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                "model_version": EMBED_MODEL,
                "score": hit.get("score"),
                "metadata": {
                    "unit_id": hit.get("unit_id"),
                    "symbol_name": hit.get("symbol_name"),
                    "unit_type": hit.get("unit_type"),
                },
            }
        )
    _post(
        f"/api/rag/jobs/{job_id}/complete",
        {
            "worker_id": worker_id,
            "snapshot": snapshot,
            "model_version": EMBED_MODEL,
            "exit_code": 0,
            "metrics": {"hits": len(hits), "seconds": round(time.time() - started, 2)},
            "evidence": evidence,
        },
    )



def execute(job: dict, worker_id: str) -> None:
    job_id = job["job_id"]
    if job.get("job_type") == "rag_query":
        _execute_query(job, worker_id)
        return
    if job.get("job_type") != "rag_ingest":
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": f"unsupported job: {job.get('job_type')}"})
        return
    params = dict((job.get("payload") or {}).get("params") or {})
    params.setdefault("library_id", job.get("library_id") or "")
    command = _command(params)
    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(job_id, worker_id, 30, stop), daemon=True)
    heartbeat.start()
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int((job.get("payload") or {}).get("timeout_seconds") or 3600),
            env=dict(os.environ),
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": output[-2000:]})
            return
        snapshot = ""
        match = re.search(r"snapshot=(\S+)", output)
        if match:
            snapshot = match.group(1)
        _post(
            "/api/rag/index-bindings",
            {
                "rag_id": "code",
                "library_id": str(job.get("library_id") or params.get("library_id") or ""),
                "index_name": "code_units",
                "embedding_model": EMBED_MODEL,
                "dimension": DIMENSION,
                "snapshot": snapshot,
                "status": "active",
            },
        )
        completed = _post(
            f"/api/rag/jobs/{job_id}/complete",
            {
                "worker_id": worker_id,
                "snapshot": snapshot,
                "model_version": EMBED_MODEL,
                "exit_code": proc.returncode,
                "metrics": {"seconds": round(time.time() - started, 2)},
            },
        )
        run_id = str(completed.get("run_id") or "")
        if run_id:
            _write_manifest(job, run_id, params, snapshot, time.time() - started)
    finally:
        stop.set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default=socket.gethostname())
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not TOKEN:
        raise SystemExit("SCIPAL_RAG_WORKER_TOKEN is required")
    while True:
        body = _post("/api/rag/jobs/lease", {"worker_id": args.worker_id, "lease_seconds": args.lease_seconds})
        job = body.get("job")
        if job:
            execute(job, args.worker_id)
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
