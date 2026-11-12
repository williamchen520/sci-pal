"""E2: DSH-like grep/read baseline vs code_search.

Uses git grep (available on Windows) as the grep engine; DSH's native grep
tool is ripgrep, so record this as a grep-equivalent baseline, not a full
DSH agent session.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

from eval.code_rag_stack.harness import ndcg_at_k, rank, summarize

REPOS = {
    "lib_2c5709b07c77": Path(r"G:/repos/scanpy-1.12.5"),
    "lib_12473817b941": Path(r"G:/repos/rnaseq-3.28.0"),
}
STOP = {
    "the", "and", "for", "with", "from", "per", "by", "to", "of", "in", "on",
    "file", "files", "data", "read", "write", "compute", "process", "raw",
}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in STOP]


def git_grep(query: str, repo: Path) -> tuple[list[str], float]:
    words = tokens(query)
    if not words:
        return [], 0.0
    pattern = "|".join(rf"\b{re.escape(word)}\b" for word in words)
    started = time.perf_counter()
    proc = subprocess.run(
        ["git", "-C", str(repo), "grep", "-c", "-I", "-i", "-E", pattern, "--", "."],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    latency = (time.perf_counter() - started) * 1000
    if proc.returncode not in (0, 1):
        return [], latency
    scored = []
    for line in proc.stdout.splitlines():
        path, _, count = line.rpartition(":")
        if path and count.isdigit():
            scored.append((int(count), path.removeprefix("./")))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored], latency


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).resolve().parent.parent / "code_rag_30.json"))
    parser.add_argument("--json", default="")
    parser.add_argument("--log", default="")
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    from sentence_transformers import SentenceTransformer
    from code_rag.search import MODEL, search

    model = SentenceTransformer(MODEL, device="cuda")
    rows = []
    logs = []
    for case in cases:
        repo = REPOS[case["library_id"]]
        paths, grep_ms = git_grep(case["query"], repo)
        read_started = time.perf_counter()
        reads = []
        for path in paths[:3]:
            target = repo / path
            if target.exists():
                target.read_text(encoding="utf-8", errors="replace")[:4000]
                reads.append(path)
        base_latency = grep_ms + (time.perf_counter() - read_started) * 1000
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "arm": "B1_git_grep_read",
                "file_rank": rank(paths, case["expected_path"]),
                "symbol_rank": None,
                "file_ndcg10": ndcg_at_k(paths, case["expected_path"], 10),
                "latency_ms": round(base_latency, 2),
                "tool_calls": 1 + len(reads),
            }
        )
        logs.append(
            {
                "arm": "B1_git_grep_read",
                "query": case["query"],
                "repo": str(repo),
                "paths": paths[:20],
                "reads": reads,
                "grep_ms": round(grep_ms, 2),
            }
        )
        started = time.perf_counter()
        hits = search(case["query"], library_id=case["library_id"], top_k=10, model=model)
        code_paths = list(dict.fromkeys(hit["path"] for hit in hits))
        code_symbols = [hit["symbol_name"] for hit in hits]
        latency = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "arm": "C1_search",
                "file_rank": rank(code_paths, case["expected_path"]),
                "symbol_rank": rank(code_symbols, case["expected_symbol"]),
                "file_ndcg10": ndcg_at_k(code_paths, case["expected_path"], 10),
                "latency_ms": round(latency, 2),
                "tool_calls": 1,
            }
        )
        logs.append(
            {
                "arm": "C1_search",
                "query": case["query"],
                "paths": code_paths,
                "symbols": code_symbols,
                "latency_ms": round(latency, 2),
            }
        )

    output = {
        "baseline_engine": "git grep (DSH grep equivalent, not full DSH session)",
        "summaries": {
            "B1_git_grep_read": summarize([row for row in rows if row["arm"] == "B1_git_grep_read"]),
            "C1_search": summarize([row for row in rows if row["arm"] == "C1_search"]),
        },
        "rows": rows,
    }
    print(json.dumps(output["summaries"], ensure_ascii=False, indent=2))
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
