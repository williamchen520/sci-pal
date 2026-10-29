"""SciFact abstract-level retrieval benchmark (standalone smoke test).

Build:
    python -m eval.scifact_benchmark --build --data-dir G:\\runs\\scifact_data\\data

Run:
    python -m eval.scifact_benchmark --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = Path(r"G:\runs\scifact_data\data")
DEFAULT_DB = ROOT / "data" / "benchmark_scifact.db"
DEFAULT_OUT = ROOT / "eval" / "results" / "scifact_smoke.json"

SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def split_sentences(text: str) -> List[str]:
    return [part.strip() for part in SENT_RE.split(text or "") if part.strip()]


def build_db(data_dir: Path, db_path: Path) -> Dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE papers (doc_id TEXT PRIMARY KEY, title TEXT, abstract TEXT);
        CREATE TABLE sentences (
            sentence_id TEXT PRIMARY KEY, doc_id TEXT, seq INTEGER, text TEXT
        );
        CREATE VIRTUAL TABLE sentences_fts USING fts5(
            sentence_id, doc_id, text
        );
        CREATE TABLE claims (
            claim_id TEXT PRIMARY KEY, claim TEXT,
            cited_doc_ids TEXT, evidence TEXT, label TEXT
        );
        """
    )
    papers = 0
    sentence_count = 0
    for line in (data_dir / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        doc_id = str(item["doc_id"])
        abstract = item.get("abstract") or []
        text = " ".join(str(part) for part in abstract)
        conn.execute(
            "INSERT INTO papers VALUES (?, ?, ?)",
            (doc_id, item.get("title") or "", text),
        )
        for seq, sentence in enumerate(split_sentences(text)):
            sentence_id = f"{doc_id}_s{seq}"
            conn.execute(
                "INSERT INTO sentences VALUES (?, ?, ?, ?)",
                (sentence_id, doc_id, seq, sentence),
            )
            conn.execute(
                "INSERT INTO sentences_fts VALUES (?, ?, ?)",
                (sentence_id, doc_id, sentence),
            )
            sentence_count += 1
        papers += 1

    claims = 0
    for filename in ("claims_train.jsonl",):
        for line in (data_dir / filename).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            evidence = item.get("evidence") or {}
            if not evidence:
                continue
            labels = sorted(
                {entry.get("label") for entries in evidence.values() for entry in entries}
            )
            conn.execute(
                "INSERT INTO claims VALUES (?, ?, ?, ?, ?)",
                (
                    str(item["id"]),
                    item["claim"],
                    json.dumps(item.get("cited_doc_ids") or []),
                    json.dumps(evidence),
                    ",".join(label for label in labels if label),
                ),
            )
            claims += 1
    conn.commit()
    conn.close()
    return {"papers": papers, "sentences": sentence_count, "claims": claims}


def search(conn: sqlite3.Connection, claim: str, top_k: int = 10):
    terms = [token for token in TOKEN_RE.findall(claim) if len(token) > 1][:12]
    if not terms:
        return []
    match = " OR ".join(f'"{term}"' for term in terms)
    rows = conn.execute(
        "SELECT sentence_id, doc_id, bm25(sentences_fts) AS rank "
        "FROM sentences_fts WHERE sentences_fts MATCH ? "
        "ORDER BY rank LIMIT 100",
        (match,),
    ).fetchall()
    best: Dict[str, float] = {}
    for sentence_id, doc_id, rank in rows:
        score = -float(rank)
        best[doc_id] = max(best.get(doc_id, float("-inf")), score)
    ordered = sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_k]
    docs = [{"doc_id": doc_id, "score": score} for doc_id, score in ordered]
    return docs, {sentence_id for sentence_id, _, _ in rows}


def run(db_path: Path, limit: int, output: Path) -> Dict:
    conn = sqlite3.connect(str(db_path))
    claims = conn.execute("SELECT * FROM claims ORDER BY claim_id LIMIT ?", (limit,)).fetchall()
    doc_recall = 0
    sent_recall = 0
    reciprocal_ranks = []
    rows = []
    for claim_id, claim, cited, evidence_json, label in claims:
        gold_docs = {str(item) for item in json.loads(cited)}
        evidence = json.loads(evidence_json)
        gold_sentences = set()
        for doc_id, entries in evidence.items():
            for entry in entries:
                for index in entry.get("sentences") or []:
                    gold_sentences.add(f"{doc_id}_s{index}")
        results, returned_sentences = search(conn, claim, top_k=10)
        returned_docs = [item["doc_id"] for item in results]
        doc_hit = bool(set(returned_docs) & gold_docs)
        doc_recall += int(doc_hit)
        rank = next(
            (index + 1 for index, doc in enumerate(returned_docs) if doc in gold_docs),
            None,
        )
        if rank:
            reciprocal_ranks.append(1.0 / rank)
        sent_hit = bool(returned_sentences & gold_sentences)
        sent_recall += int(sent_hit)
        rows.append(
            {
                "claim_id": claim_id,
                "claim": claim,
                "label": label,
                "doc_hit": doc_hit,
                "sentence_hit": sent_hit,
                "gold_docs": sorted(gold_docs),
                "returned_docs": returned_docs,
            }
        )
    conn.close()
    n = len(rows)
    summary = {
        "claims": n,
        "doc_recall@10": round(doc_recall / n, 4) if n else 0.0,
        "sentence_recall@10": round(sent_recall / n, 4) if n else 0.0,
        "mrr": round(sum(reciprocal_ranks) / n, 4) if n else 0.0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    if args.build:
        print(build_db(Path(args.data_dir), Path(args.db)))
    print(run(Path(args.db), args.limit, Path(args.output)))


if __name__ == "__main__":
    main()
