"""P6: 30-question code retrieval evaluation.

Baseline is a grep-like lexical scan over file units (DSH baseline proxy).
Code arm is the library-scoped hybrid search.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import psycopg
from sentence_transformers import SentenceTransformer

from code_rag.search import MODEL, search

STOP = {
    "the", "and", "for", "with", "from", "per", "by", "to", "of", "in", "on",
    "file", "files", "data", "read", "write", "compute", "process", "raw",
}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in STOP]


def load_files(conn, library_id: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT f.path, u.text FROM code_rag.code_units u "
        "JOIN code_rag.code_files f ON f.file_id=u.file_id "
        "WHERE u.library_id=%s AND u.unit_type='file'",
        (library_id,),
    ).fetchall()
    return [(row[0], row[1] or "") for row in rows]


def baseline(query: str, files: list[tuple[str, str]]) -> list[str]:
    words = tokens(query)
    if not words:
        return [path for path, _ in files]
    scored = []
    for path, text in files:
        lower = text.lower()
        path_lower = path.lower()
        score = 0
        for word in words:
            score += min(lower.count(word), 40)
            score += 8 * path_lower.count(word)
        if score:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored]


def rank_of(items: list[str], target: str) -> int | None:
    for i, item in enumerate(items, 1):
        if item == target:
            return i
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).with_name("code_rag_30.json")))
    parser.add_argument("--json", default="")
    parser.add_argument("--dsn", default="")
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    dsn = args.dsn or __import__("os").environ.get("SCIPAL_CODE_READ_DSN") or __import__("os").environ.get("SCIPAL_CODE_DSN", "")
    if not dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    model = SentenceTransformer(MODEL, device="cuda")
    files_by_library: dict[str, list[tuple[str, str]]] = {}
    with psycopg.connect(dsn) as conn:
        for library_id in {case["library_id"] for case in cases}:
            files_by_library[library_id] = load_files(conn, library_id)

    rows = []
    for case in cases:
        hits = search(case["query"], library_id=case["library_id"], top_k=10, model=model)
        code_paths = []
        for hit in hits:
            if hit["path"] not in code_paths:
                code_paths.append(hit["path"])
        code_symbols = [hit["symbol_name"] for hit in hits]
        base_paths = baseline(case["query"], files_by_library[case["library_id"]])
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "query": case["query"],
                "code_file_rank": rank_of(code_paths, case["expected_path"]),
                "code_symbol_rank": rank_of(code_symbols, case["expected_symbol"]),
                "baseline_file_rank": rank_of(base_paths, case["expected_path"]),
            }
        )

    def rate(key: str, cutoff: int) -> float:
        return sum(1 for row in rows if row[key] is not None and row[key] <= cutoff) / len(rows)

    summary = {
        "queries": len(rows),
        "code_file_hit@1": rate("code_file_rank", 1),
        "code_file_hit@3": rate("code_file_rank", 3),
        "code_file_hit@5": rate("code_file_rank", 5),
        "code_symbol_hit@1": rate("code_symbol_rank", 1),
        "code_symbol_hit@5": rate("code_symbol_rank", 5),
        "baseline_file_hit@1": rate("baseline_file_rank", 1),
        "baseline_file_hit@3": rate("baseline_file_rank", 3),
        "baseline_file_hit@5": rate("baseline_file_rank", 5),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
