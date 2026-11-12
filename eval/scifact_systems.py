"""SciFact system baselines: BM25, dense, hybrid RRF on the same F0 units."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from eval.scifact_phase_c import QUERY_PREFIX, build_units, encode_units, load_claims, load_sentences
from eval.scifact_units import Unit

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def build_bm25(units: list[Unit]) -> tuple[dict[str, list[tuple[int, int]]], np.ndarray, float]:
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    lengths = np.zeros(len(units), dtype=np.float32)
    for index, unit in enumerate(units):
        counts = Counter(tokenize(unit.text))
        lengths[index] = sum(counts.values())
        for token, count in counts.items():
            postings[token].append((index, count))
    return postings, lengths, float(lengths.mean() or 1.0)


def bm25_scores(
    query: str,
    postings: dict[str, list[tuple[int, int]]],
    lengths: np.ndarray,
    avgdl: float,
    n_docs: int,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> np.ndarray:
    scores = np.zeros(n_docs, dtype=np.float32)
    for token in set(tokenize(query)):
        matches = postings.get(token)
        if not matches:
            continue
        df = len(matches)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        for index, tf in matches:
            denom = tf + k1 * (1.0 - b + b * lengths[index] / avgdl)
            scores[index] += idf * tf * (k1 + 1.0) / denom
    return scores


def rank_order(scores: np.ndarray, top_n: int) -> list[int]:
    if top_n >= len(scores):
        return list(np.argsort(-scores))
    candidates = np.argpartition(-scores, top_n)[:top_n]
    return [int(index) for index in candidates[np.argsort(-scores[candidates])]]


def metrics(
    claims: list[dict],
    units: list[Unit],
    orders: list[list[int]],
    *,
    top_k: int = 10,
) -> dict:
    hit1 = hit5 = hit10 = 0
    recall = 0.0
    context_recall = 0.0
    rr = 0.0
    ndcg = 0.0
    rows = []
    for claim, order in zip(claims, orders):
        gold = set(claim["evidence"])
        first = None
        found = set()
        context_found = set()
        for rank, index in enumerate(order[:top_k], 1):
            unit = units[index]
            overlap = gold & set(unit.anchors)
            if overlap and first is None:
                first = rank
            found |= overlap
            context_found |= gold & (set(unit.anchors) | set(unit.context))
        hit1 += int(first == 1)
        hit5 += int(first is not None and first <= 5)
        hit10 += int(first is not None and first <= 10)
        recall += len(found) / max(len(gold), 1)
        context_recall += len(context_found) / max(len(gold), 1)
        rr += 1.0 / first if first else 0.0
        ndcg += 1.0 / math.log2(first + 1) if first else 0.0
        rows.append({"claim_id": claim["claim_id"], "first_rank": first})
    n = len(claims)
    return {
        "claims": n,
        "hit@1": hit1 / n,
        "hit@5": hit5 / n,
        "hit@10": hit10 / n,
        "sentence_recall@10": recall / n,
        "context_recall@10": context_recall / n,
        "mrr@10": rr / n,
        "ndcg@10": ndcg / n,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "data" / "benchmark_scifact.db"))
    parser.add_argument("--gold", default=str(Path(__file__).resolve().parent.parent / "eval" / "gold" / "scifact_300.jsonl"))
    parser.add_argument("--model", default=r"G:/models/bge-base-en-v1.5")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--chunk-words", type=int, default=120)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    grouped, _ = load_sentences(Path(args.db))
    units = build_units(grouped, words=args.chunk_words)["F0"]
    claims, skipped = load_claims(Path(args.db), Path(args.gold), args.limit)

    postings, lengths, avgdl = build_bm25(units)
    model = SentenceTransformer(args.model, device="cuda")
    vectors = encode_units(
        model, units, cache=Path(__file__).resolve().parent / "cache", model_name=args.model
    )
    query_vectors = model.encode(
        [QUERY_PREFIX + claim["claim"] for claim in claims],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    dense_scores = query_vectors @ vectors.T

    systems = {"BM25": [], "Dense": [], "Hybrid": []}
    for claim, dense_row in zip(claims, dense_scores):
        bm25_order = rank_order(
            bm25_scores(claim["claim"], postings, lengths, avgdl, len(units)),
            args.top_k * 10,
        )
        dense_order = rank_order(dense_row, args.top_k * 10)
        rrf: dict[int, float] = {}
        for rank, index in enumerate(bm25_order, 1):
            rrf[index] = rrf.get(index, 0.0) + 1.0 / (60 + rank)
        for rank, index in enumerate(dense_order, 1):
            rrf[index] = rrf.get(index, 0.0) + 1.0 / (60 + rank)
        hybrid_order = [index for index, _ in sorted(rrf.items(), key=lambda item: item[1], reverse=True)]
        systems["BM25"].append(bm25_order)
        systems["Dense"].append(dense_order)
        systems["Hybrid"].append(hybrid_order)

    output = {
        "dataset": "scifact",
        "claims": len(claims),
        "skipped_claims": skipped,
        "chunk_words": args.chunk_words,
        "model": args.model,
        "systems": {
            name: metrics(claims, units, orders, top_k=args.top_k)
            for name, orders in systems.items()
        },
    }
    print(json.dumps({name: {
        key: round(value, 4) for key, value in payload.items() if key != "rows"
    } for name, payload in output["systems"].items()}, ensure_ascii=False, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
