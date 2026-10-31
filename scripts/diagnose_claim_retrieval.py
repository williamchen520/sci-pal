"""Diagnose semantic claim retrieval: queries, filters, paragraph hits."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.claims import semantic, service
from services.review.llm_client import create_llm_client
from services.search.unified_retriever import UnifiedRetriever


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--claim", default="claim_hcc_triple_os")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    conn = service.connect(args.db)
    claim = service.get_claim(conn, args.claim)
    if not claim:
        print("claim not found")
        return 1
    corpus = claim.get("corpus") or []
    print("claim:", claim["claim_id"])
    print("corpus:", len(corpus), corpus[:3], "...")
    llm = None if args.no_llm else create_llm_client()
    queries = semantic.generate_refute_queries(
        claim["claim_text"], claim.get("qualifiers") or {}, llm_client=llm
    )
    print("queries:", queries)

    retriever = UnifiedRetriever(rerank=True, routing=True, use_abstracts=False)
    for query in queries:
        print("\nQUERY:", query)
        try:
            env = retriever.retrieve(
                query,
                top_paragraphs=args.limit,
                top_figures=0,
                top_tables=0,
                top_papers=0,
                allowed_paper_ids=set(corpus) or None,
            )
        except Exception as exc:  # noqa: BLE001
            print("  ERROR:", exc)
            continue
        paragraphs = env.get("paragraphs") or []
        print("  paragraphs:", len(paragraphs))
        for paragraph in paragraphs[: args.limit]:
            para_id = paragraph.get("para_id") or paragraph.get("paragraph_id")
            sentences = conn.execute(
                "SELECT sentence_id, text FROM sentences WHERE para_id = ? ORDER BY rowid",
                (para_id,),
            ).fetchall() if para_id else []
            print(
                "  -",
                paragraph.get("paper_id"),
                para_id,
                "|",
                str(paragraph.get("text") or "")[:120].replace("\n", " "),
                "| sentences:",
                len(sentences),
            )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
