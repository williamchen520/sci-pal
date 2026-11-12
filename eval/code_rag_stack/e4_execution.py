"""E4: compile gate and optional pytest execution for retrieved units."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psycopg

CASES = [
    ("s01", "normalize total counts per cell", "normalize_total", "tests/test_normalization.py", "test_normalize_total"),
    ("s02", "read 10x h5 file", "read_10x_h5", "tests/test_read_10x.py", "test_read_10x_h5"),
    ("s03", "highly variable genes", "highly_variable_genes", "tests/test_highly_variable_genes.py", "test_highly_variable_genes"),
    ("s04", "neighbor graph construction", "neighbors", "tests/test_neighbors.py", "test_neighbors"),
    ("s05", "compute UMAP embedding", "umap", "tests/test_embedding.py", "test_umap"),
    ("s06", "leiden clustering", "leiden", "tests/test_clustering.py", "test_leiden_basic"),
    ("s07", "score gene set per cell", "score_genes", "tests/test_score_genes.py", "test_score_genes_sparse_vs_dense"),
    ("s08", "PCA principal component analysis", "pca", "tests/test_pca.py", "test_pca"),
    ("s09", "regress out covariate effects", "regress_out", "tests/test_preprocessing.py", "test_regress_out"),
    ("s10", "rank genes between groups", "rank_genes_groups", "tests/test_rank_genes_groups.py", "test_rank_genes_groups_use_raw"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--repo", default=r"G:/repos/scanpy-1.12.5")
    parser.add_argument("--target", default=r"G:/venvs/scanpy-eval-pkgs")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    from sentence_transformers import SentenceTransformer
    from code_rag.search import MODEL, search

    model = SentenceTransformer(MODEL, device="cuda")
    rows = []
    conn = psycopg.connect(args.dsn)
    for case_id, query, symbol, test_file, selector in CASES:
        hits = search(query, library_id="lib_2c5709b07c77", top_k=1, model=model)
        hit = hits[0] if hits else {}
        text = ""
        if hit:
            row = conn.execute("SELECT text FROM code_rag.code_units WHERE unit_id=%s", (hit["unit_id"],)).fetchone()
            text = row[0] if row else ""
        compile_ok = False
        compile_error = ""
        if hit and hit.get("unit_type") in {"function", "class"}:
            try:
                compile(textwrap.dedent(text), symbol, "exec")
                compile_ok = True
            except SyntaxError as exc:
                compile_error = str(exc)
        row = {
            "id": case_id,
            "query": query,
            "expected_symbol": symbol,
            "retrieved_symbol": hit.get("symbol_name", ""),
            "retrieved_path": hit.get("path", ""),
            "compile_ok": compile_ok,
            "compile_error": compile_error,
            "test_ok": None,
            "test_returncode": None,
            "test_tail": "",
        }
        if args.run_tests:
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join([args.target, str(Path(args.repo) / "src")])
            started = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--no-header", test_file, "-k", selector],
                cwd=args.repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=180,
            )
            row["test_returncode"] = proc.returncode
            row["test_ok"] = proc.returncode == 0
            row["test_seconds"] = round(time.perf_counter() - started, 2)
            row["test_tail"] = (proc.stdout + proc.stderr)[-800:]
        rows.append(row)
    conn.close()

    summary = {
        "cases": len(rows),
        "compile_pass": sum(1 for row in rows if row["compile_ok"]) / len(rows),
        "test_pass": (
            sum(1 for row in rows if row["test_ok"]) / len(rows)
            if args.run_tests else None
        ),
        "retrieval_top1": sum(1 for row in rows if row["retrieved_symbol"] == row["expected_symbol"]) / len(rows),
        "task_compile_pass": sum(
            1 for row in rows
            if row["compile_ok"] and row["retrieved_symbol"] == row["expected_symbol"]
        ) / len(rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
