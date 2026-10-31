"""Attach the pilot corpus to existing claim cards without touching decisions."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claims_pilot.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    corpus = (yaml.safe_load(Path(args.fixture).read_text(encoding="utf-8")) or {}).get("corpus") or []
    conn = sqlite3.connect(args.db)
    try:
        conn.execute("UPDATE claim_cards SET corpus_json = ?", (json.dumps(corpus),))
        conn.commit()
        print({"claims": conn.total_changes, "corpus": len(corpus)})
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
