"""Apply manually annotated boundary/counter-evidence to claim cards."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.claims import service

FIXTURE = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claim_counterexamples.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    data = yaml.safe_load(Path(args.fixture).read_text(encoding="utf-8")) or {}
    annotations = data.get("annotations") or []
    conn = service.connect(args.db)
    try:
        applied = []
        for item in annotations:
            try:
                result = service.add_evidence(
                    conn,
                    item["claim_id"],
                    item["sentence_id"],
                    item.get("relation") or "underdetermines",
                    rationale=item.get("rationale") or "",
                    strength=float(item.get("confidence") or 0.5),
                    actor="manual-annotation",
                )
                applied.append((item["claim_id"], result["sentence_id"], result["relation"]))
            except ValueError as exc:
                applied.append((item["claim_id"], item["sentence_id"], f"ERROR: {exc}"))
        print({"applied": applied})
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
