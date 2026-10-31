"""SciFact benchmark against SciPal's hybrid retrieval core (vector + FTS + rerank)."""

from __future__ import annotations

import argparse
import os
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = Path(os.environ.get("SCIPAL_SCIFACT_DATA", str(Path(__file__).resolve().parent.parent / "data" / "scifact" / "data")))
DEFAULT_DB = ROOT / "data" / "benchmark_scifact.db"
DEFAULT_CHROMA = ROOT / "data" / "benchmark_scifact_chroma"
MODEL = os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def split_sentences(text: str) -> List[str]:
    return [part.strip() for part in SENT_RE.split(text or "") if part.strip()]


def build_db(data_dir: Path, db_path: Path) -> Dict:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT,
            journal TEXT, year INTEGER, doi TEXT, parse_engine TEXT, paper_type TEXT
        );
        CREATE TABLE sections (
            section_id TEXT PRIMARY KEY, paper_id TEXT, parent_id TEXT,
            title TEXT, path TEXT, depth INTEGER
        );
        CREATE TABLE paragraphs (
            para_id TEXT PRIMARY KEY, paper_id TEXT, section_id TEXT,
            text TEXT, sequence INTEGER, page INTEGER,
            section_level1 TEXT, section_level2 TEXT, section_path TEXT
        );
        CREATE TABLE sentences (
            sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT,
            section_id TEXT, text TEXT, sequence INTEGER, page INTEGER,
            char_start INTEGER, char_end INTEGER
        );
        CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
            para_id, paper_id, section_l1, section_l2, text
        );
        CREATE TABLE claims (
            claim_id TEXT PRIMARY KEY, claim TEXT,
            cited_doc_ids TEXT, evidence TEXT
        );
        """
    )
    papers = 0
    sentences_count = 0
    for line in (data_dir / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        doc_id = str(item["doc_id"])
        paper_id = f"scifact_{doc_id}"
        abstract = " ".join(str(part) for part in (item.get("abstract") or []))
        conn.execute(
            "INSERT INTO papers VALUES (?, ?, ?, '', 0, '', 'scifact', 'claim')",
            (paper_id, item.get("title") or "", abstract),
        )
        section_id = f"{paper_id}_sec"
        para_id = f"{paper_id}_para"
        conn.execute(
            "INSERT INTO sections VALUES (?, ?, NULL, 'Abstract', 'Abstract', 1)",
            (section_id, paper_id),
        )
        conn.execute(
            "INSERT INTO paragraphs VALUES (?, ?, ?, ?, 1, NULL, 'Abstract', '', 'Abstract')",
            (para_id, paper_id, section_id, abstract),
        )
        conn.execute(
            "INSERT INTO paragraphs_fts VALUES (?, ?, 'Abstract', '', ?)",
            (para_id, paper_id, abstract),
        )
        for seq, sentence in enumerate(split_sentences(abstract)):
            sentence_id = f"{paper_id}_s{seq}"
            conn.execute(
                "INSERT INTO sentences VALUES (?, ?, ?, ?, ?, ?, NULL, 0, 0)",
                (sentence_id, para_id, paper_id, section_id, sentence, seq),
            )
            sentences_count += 1
        papers += 1
    for line in (data_dir / "claims_train.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not item.get("evidence"):
            continue
        conn.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?)",
            (
                str(item["id"]),
                item["claim"],
                json.dumps(item.get("cited_doc_ids") or []),
                json.dumps(item.get("evidence") or {}),
            ),
        )
    conn.commit()
    conn.close()
    return {"papers": papers, "sentences": sentences_count}


def build_index(db_path: Path, chroma_path: Path) -> int:
    if chroma_path.exists():
        import shutil

        shutil.rmtree(chroma_path)
    model = SentenceTransformer(MODEL)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.create_collection("paragraphs", metadata={"hnsw:space": "cosine"})
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT para_id, paper_id, text FROM paragraphs").fetchall()
    conn.close()
    ids = [row[0] for row in rows]
    texts = [row[2] or "" for row in rows]
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=[
            {"paper_id": row[1], "section_l1": "Abstract", "section_l2": ""}
            for row in rows
        ],
    )
    return len(ids)


def rrf_fuse(*rankings, k: int = 60) -> List[Dict]:
    scores: Dict[str, float] = {}
    lookup: Dict[str, Dict] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            para_id = item.get("para_id")
            if not para_id:
                continue
            item.setdefault("paper_id", (item.get("metadata") or {}).get("paper_id"))
            scores[para_id] = scores.get(para_id, 0.0) + 1.0 / (k + rank)
            lookup.setdefault(para_id, item)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [{**lookup[para_id], "rrf_score": score} for para_id, score in ordered]


def run(db_path: Path, chroma_path: Path, limit: int, output: Path, rerank: bool = False) -> Dict:
    import services.search.hybrid_search as hs
    from services.search.reranker import Reranker

    hs.DB_PATH = db_path
    hs.CHROMA_PATH = chroma_path
    searcher = hs.HybridSearch()
    reranker = Reranker() if rerank else None
    conn = sqlite3.connect(str(db_path))
    claims = conn.execute(
        "SELECT claim_id, claim, cited_doc_ids, evidence FROM claims ORDER BY claim_id LIMIT ?",
        (limit,),
    ).fetchall()
    rows = []
    doc_hits = 0
    sentence_hits = 0
    rr = []
    for claim_id, claim, cited, evidence_json in claims:
        gold_docs = {f"scifact_{item}" for item in json.loads(cited)}
        evidence = json.loads(evidence_json)
        gold_sentences = set()
        for doc_id, entries in evidence.items():
            for entry in entries:
                for index in entry.get("sentences") or []:
                    gold_sentences.add(f"scifact_{doc_id}_s{index}")
        vector = searcher.vector_search(claim, 20)
        try:
            fts = searcher.fts_search(claim, 20)
        except Exception:
            fts = []
        fused = rrf_fuse(vector, fts)[:20]
        if reranker is not None:
            fused = reranker.rerank(claim, fused, 10)
        else:
            fused = fused[:10]
        returned_docs = {item.get("paper_id") for item in fused if item.get("paper_id")}
        doc_hit = bool(returned_docs & gold_docs)
        doc_hits += int(doc_hit)
        rank = next(
            (index + 1 for index, item in enumerate(fused) if item.get("paper_id") in gold_docs),
            None,
        )
        if rank:
            rr.append(1.0 / rank)
        para_ids = [item.get("para_id") for item in fused if item.get("para_id")]
        marks = ",".join("?" * len(para_ids)) if para_ids else "''"
        returned_sentences = set()
        if para_ids:
            for row in conn.execute(
                f"SELECT sentence_id FROM sentences WHERE para_id IN ({marks})", para_ids
            ):
                returned_sentences.add(row[0])
        sent_hit = bool(returned_sentences & gold_sentences)
        sentence_hits += int(sent_hit)
        rows.append(
            {
                "claim_id": claim_id,
                "claim": claim,
                "doc_hit": doc_hit,
                "sentence_hit": sent_hit,
                "returned_docs": sorted(returned_docs),
                "gold_docs": sorted(gold_docs),
            }
        )
    conn.close()
    n = len(rows)
    summary = {
        "claims": n,
        "doc_recall@10": round(doc_hits / n, 4) if n else 0.0,
        "sentence_recall@10": round(sentence_hits / n, 4) if n else 0.0,
        "mrr": round(sum(rr) / n, 4) if n else 0.0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--build-db", action="store_true")
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "scifact_scipal_20.json"))
    args = parser.parse_args()
    if args.build_db:
        print(build_db(Path(args.data_dir), Path(args.db)))
    if args.build_index:
        print(run_scipal_index(Path(args.db), Path(args.chroma)))
    print(run(Path(args.db), Path(args.chroma), args.limit, Path(args.output), args.rerank))


def run_scipal_index(db_path: Path, chroma_path: Path) -> int:
    return build_index(db_path, chroma_path)


if __name__ == "__main__":
    main()
