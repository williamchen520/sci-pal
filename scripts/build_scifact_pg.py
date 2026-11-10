"""Build the SciFact sentence-window benchmark into a PG schema."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import psycopg
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
SQLITE = ROOT / "data" / "benchmark_scifact.db"
SCHEMA = "scifact_eval"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ["SCIPAL_PG_DSN"])
    parser.add_argument("--sqlite", default=str(SQLITE))
    parser.add_argument("--model", default=os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5"))
    parser.add_argument("--gold", default=str(ROOT / "eval" / "gold" / "scifact_300.jsonl"))
    args = parser.parse_args()

    sqlite = sqlite3.connect(args.sqlite)
    sqlite.row_factory = sqlite3.Row
    conn = psycopg.connect(args.dsn, autocommit=True)
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.execute(f"SET search_path TO {SCHEMA}, public")
    conn.execute("DROP TABLE IF EXISTS paragraph_embeddings, sentences, paragraphs, papers CASCADE")
    conn.execute(
        """
        CREATE TABLE papers (
            paper_id text PRIMARY KEY, title text, abstract text,
            journal text, year int, doi text, duplicate_of text
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE paragraphs (
            para_id text PRIMARY KEY, paper_id text, section_id text,
            text text, sequence int, page int,
            section_level1 text, section_level2 text, section_path text
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sentences (
            sentence_id text PRIMARY KEY, para_id text, paper_id text,
            section_id text, text text, sequence int, page int,
            search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
        )
        """
    )
    conn.execute("CREATE INDEX sentences_gin ON sentences USING gin (search_vector)")
    conn.execute("CREATE INDEX sentences_para ON sentences (para_id, sequence)")
    conn.execute(
        """
        CREATE TABLE paragraph_embeddings (
            para_id text PRIMARY KEY, paper_id text,
            embedding vector(768) NOT NULL
        )
        """
    )

    papers = [dict(row) for row in sqlite.execute("SELECT * FROM papers")]
    paragraphs = [dict(row) for row in sqlite.execute("SELECT * FROM paragraphs")]
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO papers VALUES (%s,%s,%s,'',0,'',NULL)",
            [(row["paper_id"], row["title"], row["abstract"]) for row in papers],
        )
        cur.executemany(
            "INSERT INTO paragraphs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [
                (
                    row["para_id"], row["paper_id"], row.get("section_id"),
                    row["text"], row.get("sequence"), row.get("page"),
                    row.get("section_level1"), row.get("section_level2"), row.get("section_path"),
                )
                for row in paragraphs
            ],
        )
        cur.executemany(
            "INSERT INTO sentences (sentence_id, para_id, paper_id, section_id, text, sequence) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            [
                (
                    row["sentence_id"], row["para_id"], row["paper_id"],
                    row.get("section_id"), row["text"], row.get("sequence"),
                )
                for row in (dict(item) for item in sqlite.execute("SELECT * FROM sentences"))
            ],
        )
        conn.commit()

    model = SentenceTransformer(args.model)
    if model.device.type == "cpu":
        try:
            model = model.to("cuda")
        except Exception:
            pass
    for start in range(0, len(paragraphs), 64):
        batch = paragraphs[start : start + 64]
        vectors = model.encode([row["text"] for row in batch], normalize_embeddings=True, batch_size=64)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO paragraph_embeddings VALUES (%s,%s,%s::vector)",
                [
                    (row["para_id"], row["paper_id"], "[" + ",".join(f"{v:.7f}" for v in vector) + "]")
                    for row, vector in zip(batch, vectors)
                ],
            )
        conn.commit()
        print("embedded", start + len(batch), "/", len(paragraphs), flush=True)
    conn.execute(
        "CREATE INDEX paragraph_embeddings_hnsw ON paragraph_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    gold = []
    for row in sqlite.execute("SELECT claim_id, claim, evidence FROM claims ORDER BY claim_id"):
        evidence = json.loads(row["evidence"] or "{}")
        sentences = []
        for doc_id, entries in evidence.items():
            for entry in entries:
                for index in entry.get("sentences") or []:
                    sentences.append(f"scifact_{doc_id}_s{index}")
        if sentences:
            gold.append(
                {
                    "id": str(row["claim_id"]),
                    "question": row["claim"],
                    "evidence": sorted(set(sentences)),
                }
            )
    Path(args.gold).parent.mkdir(parents=True, exist_ok=True)
    Path(args.gold).write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in gold), encoding="utf-8")
    print("gold", len(gold), "papers", len(papers), "paragraphs", len(paragraphs))
    conn.close()
    sqlite.close()


if __name__ == "__main__":
    main()
