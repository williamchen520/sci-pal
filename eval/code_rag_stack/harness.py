"""E0 code-RAG evaluation harness.

Runs retrieval arms, records tool calls and latency, and scores L1.
DSH multi-turn answers are intentionally out of scope here; this harness
measures the retrieval layer only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psycopg

STOP = {
    "the", "and", "for", "with", "from", "per", "by", "to", "of", "in", "on",
    "file", "files", "data", "read", "write", "compute", "process", "raw",
}


def tokens(text: str) -> list[str]:
    import re

    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in STOP]


def rank(items: list[str], target: str) -> int | None:
    for i, item in enumerate(items, 1):
        if item == target:
            return i
    return None


def ndcg_at_k(items: list[str], target: str, k: int = 10) -> float:
    position = rank(items[:k], target)
    if position is None:
        return 0.0
    return 1.0 / math.log2(position + 1)


@dataclass
class ToolCall:
    tool: str
    args: dict
    latency_ms: float
    ok: bool = True


@dataclass
class ArmResult:
    arm: str
    query: str
    library_id: str
    paths: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""


def load_files(conn, library_id: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT f.path, u.text FROM code_rag.code_units u "
        "JOIN code_rag.code_files f ON f.file_id=u.file_id "
        "WHERE u.library_id=%s AND u.unit_type='file'",
        (library_id,),
    ).fetchall()
    return [(row[0], row[1] or "") for row in rows]


def baseline_rank(query: str, files: list[tuple[str, str]]) -> list[str]:
    words = tokens(query)
    scored = []
    for path, text in files:
        lower = text.lower()
        score = 0
        for word in words:
            score += min(lower.count(word), 40)
            score += 8 * path.lower().count(word)
        if score:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored]


def run_baseline(query: str, library_id: str, files: list[tuple[str, str]], *, read_top: int = 3) -> ArmResult:
    started = time.perf_counter()
    result = ArmResult(arm="B1_grep_read", query=query, library_id=library_id)
    t0 = time.perf_counter()
    paths = baseline_rank(query, files)
    result.calls.append(ToolCall("grep", {"query": query}, (time.perf_counter() - t0) * 1000))
    result.paths = paths
    for path in paths[:read_top]:
        t = time.perf_counter()
        next((text for p, text in files if p == path), None)
        result.calls.append(ToolCall("read", {"path": path}, (time.perf_counter() - t) * 1000))
    result.latency_ms = (time.perf_counter() - started) * 1000
    return result


def run_code(query: str, library_id: str, *, model, top_k: int = 10, trace: bool = False) -> ArmResult:
    from code_rag.search import search
    from code_rag.trace import trace as graph_trace

    started = time.perf_counter()
    arm = "C2_search_trace" if trace else "C1_search"
    result = ArmResult(arm=arm, query=query, library_id=library_id)
    t0 = time.perf_counter()
    hits = search(query, library_id=library_id, top_k=top_k, model=model)
    result.calls.append(ToolCall("code_search", {"query": query, "top_k": top_k}, (time.perf_counter() - t0) * 1000))
    result.paths = list(dict.fromkeys(hit["path"] for hit in hits))
    result.symbols = [hit["symbol_name"] for hit in hits]
    if trace and hits:
        t = time.perf_counter()
        try:
            graph_trace(unit_id=hits[0]["unit_id"], library_id=library_id, max_hops=1)
            result.calls.append(
                ToolCall("code_trace", {"unit_id": hits[0]["unit_id"], "max_hops": 1}, (time.perf_counter() - t) * 1000)
            )
        except Exception as exc:  # noqa: BLE001
            result.calls.append(ToolCall("code_trace", {"unit_id": hits[0]["unit_id"]}, (time.perf_counter() - t) * 1000, False))
            result.error = str(exc)
    result.latency_ms = (time.perf_counter() - started) * 1000
    return result


def score_row(case: dict, result: ArmResult) -> dict:
    file_rank = rank(result.paths, case["expected_path"])
    symbol_rank = rank(result.symbols, case["expected_symbol"])
    return {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "arm": result.arm,
        "file_rank": file_rank,
        "symbol_rank": symbol_rank,
        "file_ndcg10": ndcg_at_k(result.paths, case["expected_path"], 10),
        "latency_ms": round(result.latency_ms, 2),
        "tool_calls": len(result.calls),
        "error": result.error,
    }


def summarize(rows: list[dict]) -> dict:
    def rate(key: str, cutoff: int) -> float:
        return sum(1 for row in rows if row[key] is not None and row[key] <= cutoff) / max(len(rows), 1)

    return {
        "cases": len(rows),
        "file_hit@1": rate("file_rank", 1),
        "file_hit@3": rate("file_rank", 3),
        "file_hit@5": rate("file_rank", 5),
        "symbol_hit@1": rate("symbol_rank", 1),
        "symbol_hit@5": rate("symbol_rank", 5),
        "mrr": sum(1.0 / row["file_rank"] for row in rows if row["file_rank"]) / max(len(rows), 1),
        "ndcg@10": sum(row["file_ndcg10"] for row in rows) / max(len(rows), 1),
        "p50_latency_ms": sorted(row["latency_ms"] for row in rows)[len(rows) // 2] if rows else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).resolve().parent.parent / "code_rag_30.json"))
    parser.add_argument("--arms", default="baseline,code,code_trace")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    model = None
    if any(arm in {"code", "code_trace"} for arm in arms):
        from sentence_transformers import SentenceTransformer
        from code_rag.search import MODEL

        model = SentenceTransformer(MODEL, device="cuda")

    files_by_library: dict[str, list[tuple[str, str]]] = {}
    with psycopg.connect(args.dsn) as conn:
        for library_id in {case["library_id"] for case in cases}:
            files_by_library[library_id] = load_files(conn, library_id)

    run_id = uuid.uuid4().hex[:12]
    rows_all = []
    logs = []
    for arm in arms:
        for case in cases:
            if arm == "baseline":
                result = run_baseline(case["query"], case["library_id"], files_by_library[case["library_id"]])
            else:
                result = run_code(
                    case["query"],
                    case["library_id"],
                    model=model,
                    trace=arm == "code_trace",
                )
            row = score_row(case, result)
            row["run_id"] = run_id
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            rows_all.append(row)
            logs.append(
                {
                    "run_id": run_id,
                    "arm": result.arm,
                    "query": result.query,
                    "library_id": result.library_id,
                    "tool_calls": [call.__dict__ for call in result.calls],
                    "latency_ms": result.latency_ms,
                    "paths": result.paths,
                    "symbols": result.symbols,
                }
            )

    # Explicit arm grouping avoids prefix ambiguity between C1 and C2.
    summaries = {}
    for arm in arms:
        group = {
            "baseline": "B1_grep_read",
            "code": "C1_search",
            "code_trace": "C2_search_trace",
        }[arm]
        summaries[arm] = summarize([row for row in rows_all if row["arm"] == group])

    output = {"run_id": run_id, "summaries": summaries, "rows": rows_all}
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.log:
        Path(args.log).write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in logs) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
