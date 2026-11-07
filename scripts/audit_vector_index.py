#!/usr/bin/env python3
"""Audit (and optionally remove) non-indexable paragraph embeddings."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db.pg_pool import pg_connection
from services.ingest_quality.paragraph_filter import index_skip_reason


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reasons", default="")
    parser.add_argument("--out", default="G:/runs/vector_index_audit.json")
    args = parser.parse_args()
    selected = {part.strip() for part in args.reasons.split(",") if part.strip()}
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT e.para_id, p.text, p.section_level1, p.section_level2 "
            "FROM paragraph_embeddings e JOIN paragraphs p USING (para_id)"
        ).fetchall()
        flagged = []
        reasons = Counter()
        for row in rows:
            reason = index_skip_reason(
                row["text"] or "", row["section_level1"] or "", row["section_level2"] or ""
            )
            if reason:
                reasons[reason] += 1
                if not selected or reason in selected:
                    flagged.append((row["para_id"], reason))
        report = {
            "total": len(rows),
            "flagged": len(flagged),
            "pct": round(100 * len(flagged) / max(len(rows), 1), 2),
            "reasons": dict(reasons),
        }
        if args.apply and flagged:
            with pg.cursor() as cur:
                for start in range(0, len(flagged), 2000):
                    ids = [row[0] for row in flagged[start:start + 2000]]
                    cur.execute("DELETE FROM paragraph_embeddings WHERE para_id = ANY(%s)", (ids,))
            pg.commit()
            report["deleted"] = len(flagged)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report)
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
