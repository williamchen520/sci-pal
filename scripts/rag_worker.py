#!/usr/bin/env python3
"""R3 local RAG worker: lease, execute code_ingest, register binding, complete."""

from __future__ import annotations

import argparse
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


def _heartbeat(job_id: str, worker_id: str, seconds: int, stop: threading.Event) -> None:
    while not stop.wait(seconds):
        try:
            _post(f"/api/rag/jobs/{job_id}/heartbeat", {"worker_id": worker_id, "lease_seconds": 120})
        except Exception:
            return


def execute(job: dict, worker_id: str) -> None:
    job_id = job["job_id"]
    if job.get("job_type") != "rag_ingest":
        _post(f"/api/rag/jobs/{job_id}/fail", {"worker_id": worker_id, "error": f"unsupported job: {job.get('job_type')}"})
        return
    params = (job.get("payload") or {}).get("params") or {}
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
                "library_id": str(params.get("library_id") or ""),
                "index_name": "code_units",
                "embedding_model": EMBED_MODEL,
                "dimension": DIMENSION,
                "snapshot": snapshot,
                "status": "active",
            },
        )
        _post(
            f"/api/rag/jobs/{job_id}/complete",
            {
                "worker_id": worker_id,
                "snapshot": snapshot,
                "model_version": EMBED_MODEL,
                "exit_code": proc.returncode,
                "metrics": {"seconds": round(time.time() - started, 2)},
            },
        )
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
