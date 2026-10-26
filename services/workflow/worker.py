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
        run_dir = payload.get("run_dir")
        if not run_dir:
            log(f"skip {job_path.name}: missing run_dir")
            continue

        result: dict[str, Any] = {"job": job_path.name, "run_dir": run_dir}
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

        (processed / f"{job_path.name}.result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job_path.unlink()
        handled += 1
    return handled


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="services.workflow.worker")
    parser.add_argument("--queue-dir", default=str(DEFAULT_QUEUE))
    parser.add_argument("--once", action="store_true", help="process the queue once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="idle poll interval (seconds)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    print(f"worker watching {args.queue_dir}")
    while True:
        handled = process_once(args.queue_dir)
        if args.once:
            return 0
        if not handled:
            time.sleep(args.interval)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
