"""Ingest one pinned repository into scipal_code (P2).

No embeddings yet: P2 is AST/tree-sitter boundaries and graph edges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import psycopg

from code_rag.parsers import parse_nextflow, parse_python, parse_r, parse_rmd


def stable(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def repo_commit(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def scoped_unit_id(library_id: str, snapshot_id: str, parsed_unit_id: str) -> str:
    """Unit ids must not collide when two libraries contain the same path."""
    return stable("unit", library_id, snapshot_id, parsed_unit_id)


def file_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".r", ".rmd", ".qmd"}:
        return "rmd" if suffix in {".rmd", ".qmd"} else "r"
    if suffix == ".nf" or path.name == "nextflow.config":
        return "nextflow"
    return "unknown"


def files_for(repo: Path, language: str, limit: int) -> list[Path]:
    if language == "auto":
        patterns = ["**/*.py", "**/*.R", "**/*.r", "**/*.Rmd", "**/*.qmd", "**/*.nf", "**/nextflow.config"]
    elif language == "python":
        patterns = ["**/*.py"]
    elif language == "nextflow":
        patterns = ["**/*.nf", "**/nextflow.config", "**/*.config"]
    elif language == "r":
        patterns = ["**/*.R", "**/*.r"]
    elif language == "rmd":
        patterns = ["**/*.Rmd", "**/*.qmd"]
    else:
        raise SystemExit(f"unsupported language: {language}")
    found = []
    for pattern in patterns:
        found.extend(repo.glob(pattern))
    result = []
    for path in sorted(set(found)):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        result.append(path)
        if limit and len(result) >= limit:
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--ref", default="")
    parser.add_argument("--language", choices=["python", "nextflow", "r", "rmd", "auto"], required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    repo = Path(args.repo)
    commit = repo_commit(repo)
    source_id = stable("src", args.library_id, args.repo_url)
    snapshot_id = stable("snap", source_id, commit)
    files = files_for(repo, args.language, args.limit)

    with psycopg.connect(args.dsn) as conn:
        conn.execute(
            """
            INSERT INTO code_rag.code_sources (source_id, library_id, repo_url, ref, license)
            VALUES (%s,%s,%s,%s,'')
            ON CONFLICT (source_id) DO UPDATE SET ref=EXCLUDED.ref
            """,
            (source_id, args.library_id, args.repo_url, args.ref),
        )
        conn.execute(
            """
            INSERT INTO code_rag.code_snapshots
              (snapshot_id, source_id, library_id, commit_sha, ref)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (snapshot_id) DO NOTHING
            """,
            (snapshot_id, source_id, args.library_id, commit, args.ref),
        )
        conn.execute(
            "DELETE FROM code_rag.code_edges WHERE library_id=%s AND src_unit_id LIKE %s",
            (args.library_id, f"unit_%"),
        )
        conn.execute(
            "DELETE FROM code_rag.code_units WHERE snapshot_id=%s", (snapshot_id,)
        )
        run = conn.execute(
            "INSERT INTO code_rag.code_ingest_runs (library_id,snapshot_id,status) "
            "VALUES (%s,%s,'running') RETURNING run_id",
            (args.library_id, snapshot_id),
        ).fetchone()[0]

        total_units = total_edges = 0
        for path in files:
            rel = path.relative_to(repo).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            language = file_language(path) if args.language == "auto" else args.language
            if language == "python":
                units, edges = parse_python(text, rel)
            elif language == "r":
                units, edges = parse_r(text, rel)
            elif language == "rmd":
                units, edges = parse_rmd(text, rel)
            elif language == "nextflow":
                units, edges = parse_nextflow(text, rel)
            else:
                units, edges = parse_rmd(text, rel)
            file_id = stable("file", snapshot_id, rel)
            conn.execute(
                """
                INSERT INTO code_rag.code_files
                  (file_id, snapshot_id, library_id, path, language, content_hash)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (snapshot_id, path) DO UPDATE SET content_hash=EXCLUDED.content_hash
                """,
                (
                    file_id,
                    snapshot_id,
                    args.library_id,
                    rel,
                    language,
                    hashlib.sha256(text.encode()).hexdigest(),
                ),
            )
            unit_ids = {
                unit.unit_id: scoped_unit_id(args.library_id, snapshot_id, unit.unit_id)
                for unit in units
            }
            for unit in units:
                conn.execute(
                    """
                    INSERT INTO code_rag.code_units
                      (unit_id, snapshot_id, library_id, file_id, symbol_name,
                       unit_type, text, start_line, end_line, parent_unit_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (unit_id) DO NOTHING
                    """,
                    (
                        unit_ids[unit.unit_id],
                        snapshot_id,
                        args.library_id,
                        file_id,
                        unit.symbol_name,
                        unit.unit_type,
                        unit.text,
                        unit.start_line,
                        unit.end_line,
                        unit_ids.get(unit.parent_unit_id, unit.parent_unit_id),
                    ),
                )
                total_units += 1
            for edge in edges:
                conn.execute(
                    """
                    INSERT INTO code_rag.code_edges
                      (src_unit_id, dst_unit_id, library_id, relation, source, confidence)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        unit_ids.get(edge.src_unit_id, edge.src_unit_id),
                        unit_ids.get(edge.dst_unit_id, edge.dst_unit_id),
                        args.library_id,
                        edge.relation,
                        edge.source,
                        edge.confidence,
                    ),
                )
                total_edges += 1
            if len(files) >= 100 and files.index(path) % 100 == 0:
                print(f"progress files={files.index(path)} units={total_units}", flush=True)
        conn.execute(
            "UPDATE code_rag.code_ingest_runs SET status='completed', files=%s, units=%s, "
            "finished_at=now() WHERE run_id=%s",
            (len(files), total_units, run),
        )
        conn.commit()
    print(
        f"CODE_RAG_INGEST_OK language={args.language} files={len(files)} "
        f"units={total_units} edges={total_edges} snapshot={snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
