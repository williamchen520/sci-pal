"""LitQA2 smoke benchmark: fetch source papers, build a SciPal-compatible DB, retrieve.

Only public LitQA2 questions are used; source XML is fetched from Europe PMC and
kept outside the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from build_db.jats_parser import parse_jats

DEFAULT_QUESTIONS = Path(os.environ.get("SCIPAL_LITQA2_DATA", str(ROOT / "data" / "lab-bench" / "LitQA2" / "litqa-v2-public.jsonl")))
DEFAULT_DB = ROOT / "data" / "benchmark_litqa2.db"
DEFAULT_CHROMA = ROOT / "data" / "benchmark_litqa2_chroma"
MODEL = os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str) -> List[str]:
    return [part.strip() for part in SENT_RE.split(text or "") if part.strip()]


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("‐", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\([0-9,\-\s]+\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def match_key_passage(key_passage: str, sentences: List[Dict]) -> Dict:
    key = normalize_text(key_passage)
    if not key:
        return {}
    key_tokens = set(key.split())
    raw_key = (key_passage or "").lower().strip()
    for sentence in sentences:
        if raw_key and raw_key in (sentence["text"] or "").lower():
            return {**sentence, "method": "raw", "score": 1.0}
    for sentence in sentences:
        if key and key in normalize_text(sentence["text"]):
            return {**sentence, "method": "exact", "score": 1.0}
    best = None
    best_score = 0.0
    for sentence in sentences:
        tokens = set(normalize_text(sentence["text"]).split())
        if not tokens:
            continue
        score = len(key_tokens & tokens) / len(key_tokens)
        if score > best_score:
            best_score, best = score, sentence
    if best is not None and best_score >= 0.6:
        return {**best, "method": "overlap", "score": round(best_score, 4)}
    return {}


def fetch_xml(doi: str) -> str | None:
    query = urllib.parse.quote(f'DOI:"{doi}"')
    try:
        with urllib.request.urlopen(
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json",
            timeout=30,
        ) as response:
            data = json.loads(response.read())
        results = data.get("resultList", {}).get("result") or []
    except Exception:  # noqa: BLE001
        return None
    pmcid = next((item.get("pmcid") for item in results if item.get("pmcid")), None)
    if not pmcid:
        return None
    try:
        with urllib.request.urlopen(
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
            timeout=60,
        ) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None


def build(data: Path, limit: int, db_path: Path, chroma_path: Path) -> Dict:
    if db_path.exists():
        db_path.unlink()
    if chroma_path.exists():
        shutil.rmtree(chroma_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, doi TEXT);
        CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT, title TEXT, path TEXT, depth INTEGER);
        CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT, section_id TEXT, text TEXT, sequence INTEGER, page INTEGER, section_level1 TEXT, section_level2 TEXT);
        CREATE VIRTUAL TABLE paragraphs_fts USING fts5(para_id, paper_id, section_l1, section_l2, text);
        CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT, text TEXT, sequence INTEGER);
        CREATE TABLE claims (claim_id TEXT PRIMARY KEY, question TEXT, ideal TEXT, gold_para TEXT, gold_sentences TEXT);
        """
    )
    questions = [
        json.loads(line)
        for line in data.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:limit]
    mapped = 0
    for item in questions:
        sources = item.get("sources") or []
        doi = (sources[0] if sources else "").replace("https://doi.org/", "")
        if not doi:
            continue
        xml = fetch_xml(doi)
        if not xml:
            print("skip", item["id"], doi)
            continue
        parsed = parse_jats(xml)
        paper_id = f"litqa2_{item['id']}"
        title = (parsed.get("metadata") or {}).get("title") or item["question"][:80]
        conn.execute("INSERT INTO papers VALUES (?, ?, '', ?)", (paper_id, title, doi))
        section_ids = {}
        for section in parsed.get("sections") or []:
            sid = f"{paper_id}_{section.get('section_id') or len(section_ids)}"
            section_ids[section.get("section_id")] = sid
            conn.execute(
                "INSERT INTO sections VALUES (?, ?, ?, ?, ?)",
                (
                    sid,
                    paper_id,
                    section.get("title") or "",
                    " › ".join(section.get("path") or [])
                    if isinstance(section.get("path"), list)
                    else (section.get("path") or ""),
                    section.get("depth") or 1,
                ),
            )
        key_passage = (item.get("key-passage") or "").strip()
        gold_para = None
        gold_sentences = []
        all_sentences = []
        all_paragraphs = []
        for index, paragraph in enumerate(parsed.get("paragraphs") or []):
            para_id = f"{paper_id}_p{index}"
            text = paragraph.get("text") or ""
            if not text.strip():
                continue
            sid = section_ids.get(paragraph.get("section_id")) or f"{paper_id}_sec"
            conn.execute(
                "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, NULL, ?, '')",
                (para_id, paper_id, sid, text, index, paragraph.get("section_title") or ""),
            )
            conn.execute(
                "INSERT INTO paragraphs_fts VALUES (?, ?, ?, '', ?)",
                (para_id, paper_id, paragraph.get("section_title") or "", text),
            )
            all_paragraphs.append({"para_id": para_id, "text": text})
            for seq, sentence in enumerate(split_sentences(text)):
                sentence_id = f"{para_id}_s{seq}"
                conn.execute("INSERT INTO sentences VALUES (?, ?, ?, ?)", (sentence_id, para_id, sentence, seq))
                all_sentences.append(
                    {"sentence_id": sentence_id, "para_id": para_id, "text": sentence}
                )
        matched = match_key_passage(key_passage, all_sentences) if key_passage else {}
        if matched:
            gold_para = matched["para_id"]
            gold_sentences = [matched["sentence_id"]]
        else:
            raw_key = (key_passage or "").lower()
            for paragraph in all_paragraphs:
                if raw_key and raw_key in (paragraph["text"] or "").lower():
                    gold_para = paragraph["para_id"]
                    gold_sentences = [
                        sentence["sentence_id"]
                        for sentence in all_sentences
                        if sentence["para_id"] == gold_para
                    ]
                    break
            if gold_para is None:
                norm_key = normalize_text(key_passage)
                for paragraph in all_paragraphs:
                    if norm_key and norm_key in normalize_text(paragraph["text"]):
                        gold_para = paragraph["para_id"]
                        gold_sentences = [
                            sentence["sentence_id"]
                            for sentence in all_sentences
                            if sentence["para_id"] == gold_para
                        ]
                        break
        if gold_para is None:
            print("unmapped key-passage", item["id"])
        conn.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?, ?)",
            (item["id"], item["question"], item.get("ideal") or "", gold_para, json.dumps(gold_sentences)),
        )
        mapped += 1
    conn.commit()
    conn.close()

    model = SentenceTransformer(MODEL)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.create_collection("paragraphs", metadata={"hnsw:space": "cosine"})
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT para_id, paper_id, text FROM paragraphs").fetchall()
    conn.close()
    if rows:
        collection.add(
            ids=[row[0] for row in rows],
            embeddings=model.encode([row[2] for row in rows], batch_size=64, normalize_embeddings=True, show_progress_bar=False).tolist(),
            documents=[row[2] for row in rows],
            metadatas=[{"paper_id": row[1], "section_l1": "", "section_l2": ""} for row in rows],
        )
    return {"questions": len(questions), "mapped": mapped, "paragraphs": len(rows)}


def run(db_path: Path, chroma_path: Path, output: Path) -> Dict:
    import services.search.hybrid_search as hs

    hs.DB_PATH = db_path
    hs.CHROMA_PATH = chroma_path
    searcher = hs.HybridSearch()
    conn = sqlite3.connect(str(db_path))
    claims = conn.execute("SELECT * FROM claims").fetchall()
    doc_hits = 0
    sentence_hits = 0
    answered = 0
    rows = []
    for claim_id, question, ideal, gold_para, gold_sentences_json in claims:
        if not gold_para:
            continue
        answered += 1
        gold_sentences = set(json.loads(gold_sentences_json))
        vector = searcher.vector_search(question, 20)
        try:
            fts = searcher.fts_search(question, 20)
        except Exception:
            fts = []
        scores = {}
        lookup = {}
        for ranking in (vector, fts):
            for rank, item in enumerate(ranking, 1):
                para_id = item.get("para_id")
                if not para_id:
                    continue
                scores[para_id] = scores.get(para_id, 0.0) + 1.0 / (60 + rank)
                lookup.setdefault(para_id, item)
        fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]
        returned = [para_id for para_id, _ in fused]
        doc_hit = gold_para in returned
        doc_hits += int(doc_hit)
        returned_sentences = set()
        if returned:
            marks = ",".join("?" * len(returned))
            returned_sentences = {
                row[0]
                for row in conn.execute(
                    f"SELECT sentence_id FROM sentences WHERE para_id IN ({marks})", returned
                )
            }
        sent_hit = bool(returned_sentences & gold_sentences)
        sentence_hits += int(sent_hit)
        rows.append({"id": claim_id, "doc_hit": doc_hit, "sentence_hit": sent_hit, "returned": returned})
    conn.close()
    n = answered
    summary = {
        "answered": n,
        "doc_recall@10": round(doc_hits / n, 4) if n else 0.0,
        "sentence_recall@10": round(sentence_hits / n, 4) if n else 0.0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "litqa2_smoke_20.json"))
    args = parser.parse_args()
    if args.build:
        print(build(Path(args.questions), args.limit, Path(args.db), Path(args.chroma)))
    print(run(Path(args.db), Path(args.chroma), Path(args.output)))


if __name__ == "__main__":
    main()
