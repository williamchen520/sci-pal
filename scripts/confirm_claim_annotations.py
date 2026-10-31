"""Record human confirmation of the five boundary annotations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.claims import service

NOTES = {
    "claim_hcc_triple_os": "人工复核 2026-10-31：标注 1 正确。ICI 单药 ORR 有限是边界证据，不是 TACE 三联 vs TACE 的直接反例；保留 underdetermines。",
    "claim_hcc_dtace_haic": "人工复核 2026-10-31：标注 2 正确。MaVI 中 lenvatinib/bevacizumab 获益不一致，不是 dTACE vs HAIC 的直接反例；保留 underdetermines。",
    "claim_hcc_ici_rechallenge": "人工复核 2026-10-31：标注 3A/3B 正确。无标准方案、无头对头均削弱普遍性，但不直接否定“部分患者可能获益”；保留 underdetermines。",
    "claim_sbrt_ici_watch": "人工复核 2026-10-31：标注 4 正确。作者要求更大样本验证，属于待验证边界证据，不是 refutes；保留 underdetermines。",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    args = parser.parse_args()
    conn = service.connect(args.db)
    try:
        applied = []
        for claim_id, note in NOTES.items():
            claim = service.add_note(conn, claim_id, note, actor="human-review")
            applied.append((claim_id, claim["status"], claim["decision"]))
        print({"confirmed": applied})
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
