"""Resident workflow worker.

Keeps the retriever (and therefore the embedding + rerank models) loaded between
jobs, so repeated runs only pay the retrieval cost once. Jobs are dropped into a
queue directory as ``*.job.json``::

    {"spec": "G:/runs/job.json", "run_dir": "D:/sciPal/data/runs/2026-10-27", "approve": true}

Each job produces ``processed/<job>.result.json`` and is removed from the queue.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from services.workflow import run_workflow
from services.workflow.run import build_stages, load_spec

DEFAULT_QUEUE = Path("data/runs/_queue")


def process_once(
    queue_dir: str | Path,
    *,
    runner: Callable[..., Mapping[str, Any]] | None = None,
    stages: Mapping[str, Any] | None = None,
    ingest_executor: Callable[[str], Any] | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Process every queued job once; return how many were handled."""
    queue = Path(queue_dir)
    queue.mkdir(parents=True, exist_ok=True)
    processed = queue / "processed"
    processed.mkdir(exist_ok=True)

    handled = 0
    for job_path in sorted(queue.glob("*.job.json")):
        payload = json.loads(job_path.read_text(encoding="utf-8-sig"))

        if payload.get("type") == "ingest":
            task_id = payload.get("task_id")
            result: dict[str, Any] = {
                "job": job_path.name,
                "type": "ingest",
                "task_id": task_id,
            }
            try:
                executor = ingest_executor or run_ingest_job
                result["status"] = executor(task_id)
                log(f"{job_path.name}: ingest {task_id} -> {result['status']}")
            except Exception as exc:  # noqa: BLE001 - worker must survive a bad job
                result.update(status="failed", error=str(exc))
                log(f"{job_path.name}: ingest failed - {exc}")
            _finish(queue / "processed", job_path, result)
            handled += 1
            continue

        run_dir = payload.get("run_dir")
        if not run_dir:
            log(f"skip {job_path.name}: missing run_dir")
            continue

        result = {"job": job_path.name, "run_dir": run_dir}
        try:
            spec = load_spec(payload["spec"])
            run = runner or run_workflow
            manifest = run(
                spec,
                dict(stages) if stages is not None else build_stages(),
                run_dir=run_dir,
                approve=bool(payload.get("approve", True)),
            )
            result.update(
                status=manifest.get("status"),
                run_id=manifest.get("run_id"),
            )
            log(f"{job_path.name}: {result['status']} ({result.get('run_id')})")
        except Exception as exc:  # noqa: BLE001 - worker must survive a bad job
            result.update(status="failed", error=str(exc))
            log(f"{job_path.name}: failed - {exc}")

        _finish(queue / "processed", job_path, result)
        handled += 1
    return handled


def _finish(processed: Path, job_path: Path, result: Mapping[str, Any]) -> None:
    (processed / f"{job_path.name}.result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    job_path.unlink()


class HttpEmbedder:
    """Single-writer bridge: post paragraphs to Flask, which owns Chroma."""

    def __init__(self, base_url: str | None = None) -> None:
        import os

        self.base_url = (
            base_url or os.environ.get("SCIPAL_BASE_URL", "http://127.0.0.1:5000")
        ).rstrip("/")

    def __call__(self, rows: Sequence[Mapping[str, Any]]) -> int:
        import urllib.request

        payload = {
            "rows": [
                {
                    "para_id": row["para_id"],
                    "paper_id": row["paper_id"],
                    "text": row["text"],
                    "section": row.get("section", ""),
                }
                for row in rows
            ]
        }
        request = urllib.request.Request(
            self.base_url + "/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
        return int(body.get("count") or 0)


def run_ingest_job(task_id: str) -> str:
    """Run an ingest task inside the worker process (models reused across jobs)."""
    import os

    from services.search.ingest import IngestService

    root = Path(__file__).resolve().parents[2]
    local_embed = os.environ.get("SCIPAL_INGEST_EMBED", "").strip().lower() == "local"
    service = IngestService(
        db_path=root / "data" / "research.db",
        xml_dir=root / "documents_xml",
        chroma_path=root / "data" / "chroma",
        embed_client=None if local_embed else HttpEmbedder(),
    )
    task = service.execute(task_id)
    return (task or {}).get("status", "unknown")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="services.workflow.worker")
    parser.add_argument("--queue-dir", default=str(DEFAULT_QUEUE))
    parser.add_argument("--once", action="store_true", help="process the queue once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="idle poll interval (seconds)")
    parser.add_argument(
        "--log-file",
        default=None,
        help="append stdout/stderr to this file (used by the scheduled task)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = handle
        sys.stderr = handle

    print(f"worker watching {args.queue_dir}")
    while True:
        handled = process_once(args.queue_dir)
        if args.once:
            return 0
        if not handled:
            time.sleep(args.interval)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
