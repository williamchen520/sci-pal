"""Set the writing brief for claim_hcc_triple_os after the OS counter-evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.claims import service

BRIEF = {
    "safe_claim": (
        "在不可切除 HCC 中，TACE 联合抗 VEGF/TKI 与 PD-1/PD-L1 的方案与 PFS 改善相关；"
        "OS 数据仍不成熟，当前未显示统计学显著的 OS 获益。"
    ),
    "must_include": [
        "PFS 与 OS 必须分开写",
        "OS 数据 immature，不能说显著获益",
        "研究间异质性与方案差异",
        "LEAP-012 / EMERALD-1 的 OS 未成熟证据",
    ],
    "must_not_write": [
        "TACE 三联提高总生存",
        "TACE 三联显著改善 OS",
        "PFS 获益等同于 OS 获益",
    ],
    "evidence_ids": [
        "paper_PMC13616637_ab84d6de_xml_para_00015_sent_001",
        "paper_PMC12771288_fca97ed9_xml_para_00000_sent_001",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    args = parser.parse_args()
    conn = service.connect(args.db)
    try:
        claim = service.set_writing_brief(conn, "claim_hcc_triple_os", BRIEF, actor="human-review")
        print({"claim": claim["claim_id"], "status": claim["status"], "brief": claim["writing_brief"]})
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
