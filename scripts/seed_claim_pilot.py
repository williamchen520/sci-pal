"""Seed the 10-claim HCC immuno-oncology pilot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_db.claim_pilot_schema import migrate
from services.claims import service

DEFAULT_FIXTURE = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claims_pilot.yaml"
DEFAULT_DB = ROOT / "data" / "research.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    migrate(args.db)
    fixture = yaml.safe_load(Path(args.fixture).read_text(encoding="utf-8")) or {}
    claims = fixture.get("claims") or []
    corpus = fixture.get("corpus") or []
    conn = service.connect(args.db)
    try:
        corpus_found = 0
        for paper_id in corpus:
            row = conn.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
            if row:
                corpus_found += 1
        if args.reset:
            conn.execute("DELETE FROM claim_card_events")
            conn.execute("DELETE FROM claim_card_evidence")
            conn.execute("DELETE FROM claim_cards")
            conn.commit()
        evidence_count = 0
        papers = set()
        missing = []
        for item in claims:
            claim_id = service.create_claim(conn, item)
            for evidence in item.get("evidence") or []:
                sentence_id = evidence.get("sentence_id")
                try:
                    result = service.add_evidence(
                        conn,
                        claim_id,
                        sentence_id,
                        evidence.get("relation") or "supports",
                        rationale=evidence.get("rationale") or "",
                        strength=float(evidence.get("strength") or 0.5),
                        actor="seed",
                    )
                except ValueError as exc:
                    missing.append(f"{claim_id}: {sentence_id}: {exc}")
                    continue
                evidence_count += 1
                papers.add(result["paper_id"])
        print(
            {
                "claims": len(claims),
                "evidence": evidence_count,
                "papers_with_evidence": len(papers),
                "corpus": len(corpus),
                "corpus_found": corpus_found,
                "missing": missing,
            }
        )
        return 1 if missing else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
