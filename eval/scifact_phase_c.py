"""SciFact Phase C: fixed chunk vs window vs sentence-boundary chunk.

Arms:
  F0  500-word hard-cut chunks, no context
  B   same chunks + +/-1 sentence context (context not scored)
  C   500-word sentence-boundary chunks + +/-1 sentence context

The unit is a chunk; metrics are sentence-level against SciFact gold evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from eval.scifact_units import Sentence, Unit, boundary_chunks, context_window, hard_chunks

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "benchmark_scifact.db"
DEFAULT_GOLD = ROOT / "eval" / "gold" / "scifact_300.jsonl"
DEFAULT_MODEL = r"G:/models/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
WORD_RE = re.compile(r"\S+")


def load_sentences(db: Path) -> tuple[dict[str, list[Sentence]], dict[str, str]]:
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT sentence_id, paper_id, sequence, text FROM sentences ORDER BY paper_id, sequence"
    ).fetchall()
    titles = dict(conn.execute("SELECT paper_id, title FROM papers").fetchall())
    conn.close()
    grouped: dict[str, list[Sentence]] = {}
    for sentence_id, paper_id, ordinal, text in rows:
        grouped.setdefault(paper_id, []).append(
            Sentence(sentence_id, paper_id, int(ordinal), text or "", 0, 0)
        )
    for paper_sentences in grouped.values():
        cursor = 0
        for sentence in paper_sentences:
            sentence.start = cursor
            sentence.end = cursor + len(sentence.text)
            cursor = sentence.end + 1
    return grouped, titles


def build_units(
    grouped: dict[str, list[Sentence]], words: int = 500, include_sentence: bool = False
) -> dict[str, list[Unit]]:
    f0, b, c = [], [], []
    sentences_units: list[Unit] = []
    for paper_sentences in grouped.values():
        hard = hard_chunks(paper_sentences, words=words)
        f0.extend(hard)
        for unit in hard:
            start = next(
                item.ordinal for item in paper_sentences if item.sentence_id == unit.anchors[0]
            )
            end = next(
                item.ordinal for item in paper_sentences if item.sentence_id == unit.anchors[-1]
            )
            b.append(
                Unit(
                    unit_id=unit.unit_id.replace(":hard:", ":win:"),
                    paper_id=unit.paper_id,
                    text=unit.text,
                    anchors=unit.anchors,
                    context=context_window(paper_sentences, start, end),
                )
            )
        c.extend(boundary_chunks(paper_sentences, words=words))
        if include_sentence:
            for sentence in paper_sentences:
                sentences_units.append(
                    Unit(
                        unit_id=sentence.sentence_id,
                        paper_id=sentence.paper_id,
                        text=sentence.text,
                        anchors=(sentence.sentence_id,),
                        context=context_window(paper_sentences, sentence.ordinal, sentence.ordinal),
                    )
                )
    arms = {"F0": f0, "B": b, "C": c}
    if include_sentence:
        arms["S"] = sentences_units
    return arms


def encode_units(
    model: SentenceTransformer,
    units: list[Unit],
    *,
    cache: Path,
    model_name: str,
) -> np.ndarray:
    digest = hashlib.sha1(
        (model_name + "|" + "|".join(unit.unit_id + unit.text for unit in units)).encode()
    ).hexdigest()[:16]
    cache_file = cache / f"units_{digest}.npy"
    if cache_file.exists():
        return np.load(cache_file)
    vectors = model.encode(
        [unit.text for unit in units],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    cache.mkdir(parents=True, exist_ok=True)
    np.save(cache_file, vectors)
    return vectors


def load_claims(db: Path, gold_path: Path, limit: int) -> tuple[list[dict], list[str]]:
    gold = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            gold.append({"claim_id": str(item["id"]), "claim": item["question"], "evidence": item["evidence"]})
    conn = sqlite3.connect(str(db))
    existing = {
        str(row[0]): row[1]
        for row in conn.execute("SELECT claim_id, claim FROM claims").fetchall()
    }
    sentence_ids = {row[0] for row in conn.execute("SELECT sentence_id FROM sentences").fetchall()}
    conn.close()
    mapped = []
    skipped = []
    for item in gold:
        evidence = [sentence_id for sentence_id in item["evidence"] if sentence_id in sentence_ids]
        if len(evidence) != len(item["evidence"]):
            skipped.append(item["claim_id"])
            continue
        item["claim"] = existing.get(item["claim_id"], item["claim"])
        item["evidence"] = evidence
        mapped.append(item)
    return (mapped[:limit] if limit else mapped), skipped


def evaluate(
    claims: list[dict],
    units: list[Unit],
    vectors: np.ndarray,
    model: SentenceTransformer,
    *,
    top_k: int = 10,
    reranker: CrossEncoder | None = None,
    rerank_top: int = 20,
) -> dict:
    sentence_to_anchor = {}
    for index, unit in enumerate(units):
        for sentence_id in unit.anchors:
            sentence_to_anchor.setdefault(sentence_id, index)
    query_vectors = model.encode(
        [QUERY_PREFIX + claim["claim"] for claim in claims],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    scores = query_vectors @ vectors.T
    hit1 = hit5 = hit10 = 0
    sent_recall = 0.0
    context_recall = 0.0
    rr = 0.0
    ndcg = 0.0
    rows = []
    for claim, score_row in zip(claims, scores):
        gold = set(claim["evidence"])
        order = np.argsort(-score_row)
        if reranker is not None:
            candidates = order[:rerank_top]
            pairs = [(claim["claim"], units[int(index)].text) for index in candidates]
            rerank_scores = reranker.predict(pairs)
            order = [int(index) for _, index in sorted(zip(rerank_scores, candidates), reverse=True)]
        order = order[:top_k]
        first = None
        found = set()
        context_found = set()
        for rank, unit_index in enumerate(order, 1):
            unit = units[int(unit_index)]
            overlap = gold & set(unit.anchors)
            if overlap and first is None:
                first = rank
            found |= overlap
            context_found |= gold & (set(unit.anchors) | set(unit.context))
        hit1 += int(first == 1)
        hit5 += int(first is not None and first <= 5)
        hit10 += int(first is not None and first <= 10)
        sent_recall += len(found) / max(len(gold), 1)
        context_recall += len(context_found) / max(len(gold), 1)
        rr += 1.0 / first if first else 0.0
        ndcg += 1.0 / math.log2(first + 1) if first else 0.0
        rows.append(
            {
                "claim_id": claim["claim_id"],
                "first_rank": first,
                "gold": sorted(gold),
                "top": [units[int(index)].unit_id for index in order[:3]],
            }
        )
    n = len(claims)
    return {
        "claims": n,
        "hit@1": hit1 / n,
        "hit@5": hit5 / n,
        "hit@10": hit10 / n,
        "sentence_recall@10": sent_recall / n,
        "context_recall@10": context_recall / n,
        "mrr@10": rr / n,
        "ndcg@10": ndcg / n,
        "rows": rows,
    }



def evaluate_grouped(
    claims: list[dict],
    parent_units: list[Unit],
    sentence_units: list[Unit],
    sentence_vectors: np.ndarray,
    model: SentenceTransformer,
    *,
    top_k: int = 10,
    aggregate: str = "max",
    top_sentences: int = 2,
) -> dict:
    """Score sentences, aggregate by parent chunk, rank parent chunks."""
    parent_of = {}
    parent_by_id = {unit.unit_id: unit for unit in parent_units}
    for parent in parent_units:
        for sentence_id in parent.anchors:
            parent_of[sentence_id] = parent.unit_id
    sentence_parent = [parent_of.get(unit.anchors[0], "") for unit in sentence_units]
    query_vectors = model.encode(
        [QUERY_PREFIX + claim["claim"] for claim in claims],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    scores = query_vectors @ sentence_vectors.T
    hit1 = hit5 = hit10 = 0
    sent_recall = 0.0
    context_recall = 0.0
    rr = 0.0
    ndcg = 0.0
    rows = []
    for claim, score_row in zip(claims, scores):
        grouped: dict[str, list[float]] = {}
        for sentence_index, score in enumerate(score_row):
            parent_id = sentence_parent[sentence_index]
            if parent_id:
                grouped.setdefault(parent_id, []).append(float(score))
        best: dict[str, float] = {}
        for parent_id, values in grouped.items():
            values.sort(reverse=True)
            best[parent_id] = max(values) if aggregate == "max" else sum(values[:top_sentences])
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_k]
        gold = set(claim["evidence"])
        first = None
        found = set()
        context_found = set()
        for rank, (parent_id, _) in enumerate(ranked, 1):
            parent = parent_by_id[parent_id]
            overlap = gold & set(parent.anchors)
            if overlap and first is None:
                first = rank
            found |= overlap
            context_found |= gold & (set(parent.anchors) | set(parent.context))
        hit1 += int(first == 1)
        hit5 += int(first is not None and first <= 5)
        hit10 += int(first is not None and first <= 10)
        sent_recall += len(found) / max(len(gold), 1)
        context_recall += len(context_found) / max(len(gold), 1)
        rr += 1.0 / first if first else 0.0
        ndcg += 1.0 / math.log2(first + 1) if first else 0.0
        rows.append({"claim_id": claim["claim_id"], "first_rank": first, "gold": sorted(gold)})
    n = len(claims)
    return {
        "claims": n,
        "hit@1": hit1 / n,
        "hit@5": hit5 / n,
        "hit@10": hit10 / n,
        "sentence_recall@10": sent_recall / n,
        "context_recall@10": context_recall / n,
        "mrr@10": rr / n,
        "ndcg@10": ndcg / n,
        "rows": rows,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--chunk-words", type=int, default=500)
    parser.add_argument("--include-sentence", action="store_true")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--reranker-model", default=r"G:/models/bge-reranker-base")
    parser.add_argument("--cache", default=str(ROOT / "eval" / "cache"))
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    grouped, _ = load_sentences(Path(args.db))
    units_by_arm = build_units(
        grouped, words=args.chunk_words, include_sentence=args.include_sentence
    )
    claims, skipped = load_claims(Path(args.db), Path(args.gold), args.limit)
    model = SentenceTransformer(args.model, device="cuda")
    reranker = CrossEncoder(args.reranker_model, device="cuda") if args.rerank else None
    results = {}
    vectors_by_arm = {}
    for arm, units in units_by_arm.items():
        vectors = encode_units(model, units, cache=Path(args.cache), model_name=args.model)
        vectors_by_arm[arm] = vectors
        results[arm] = {
            "units": len(units),
            "metrics": evaluate(
                claims,
                units,
                vectors,
                model,
                top_k=args.top_k,
                reranker=reranker,
            ),
        }
    if "S" in units_by_arm and "C" in units_by_arm:
        for label, aggregate, top_sentences in (
            ("C2", "max", 1),
            ("C3", "sum", 2),
            ("C3_3", "sum", 3),
        ):
            results[label] = {
                "units": len(units_by_arm["C"]),
                "metrics": evaluate_grouped(
                    claims,
                    units_by_arm["C"],
                    units_by_arm["S"],
                    vectors_by_arm["S"],
                    model,
                    top_k=args.top_k,
                    aggregate=aggregate,
                    top_sentences=top_sentences,
                ),
            }
    output = {
        "dataset": "scifact",
        "claims": len(claims),
        "skipped_claims": skipped,
        "model": args.model,
        "chunk_words": args.chunk_words,
        "rerank": args.rerank,
        "arms": results,
    }
    print(json.dumps({k: v["metrics"] for k, v in results.items()}, ensure_ascii=False, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
