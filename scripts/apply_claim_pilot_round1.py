"""Apply the first human-confirmed claim-pilot decisions.

The notes are the audit record; they intentionally preserve limitations rather
than upgrading every claim to "accepted".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.claims import service

DECISIONS = {
    "claim_hcc_triple_os": (
        "accept",
        "第一轮：53 项研究 meta-analysis，TACE 单药对照 HR 0.54（95%CI 0.45–0.64）。接受，但仅限总体策略，不外推到具体三联方案排序。",
    ),
    "claim_hdv_hcc_signature": (
        "accept",
        "第一轮：92 种可溶性介质、FDR + MELD 校正；HDV-HCC 免疫调节型、HBV-HCC 促炎型。接受，限定单中心与全身炎症谱。",
    ),
    "claim_tcsp_prognosis": (
        "accept",
        "第一轮：TCGA-LIHC 高 TCSP 组 OS 更短（P=0.00011）。接受，限定公共队列；写相关，不写因果。",
    ),
    "claim_fabp5_immune": (
        "accept",
        "第一轮：FABP5 高表达与 CD8+ T 细胞/巨噬细胞浸润增加相关。接受，低置信度；只能写关联。",
    ),
    "claim_hcc_dtace_haic": (
        "revise",
        "第一轮：结论句支持疗效，但缺 ORR/PFS/OS、样本量、两组基线与 TRAE 数值；补充后重新提交。",
    ),
    "claim_hcc_time_immunosuppressive": (
        "revise",
        "第一轮：单细胞证据支持免疫抑制与髓系/多检查点耗竭共存，但不足以证明 driven by；改为 associated with。",
    ),
    "claim_sbrt_ici_watch": (
        "revise",
        "第一轮：29/63 CR 为单臂/选择人群；需限定该 SBRT 方案、随访策略与高度选择患者，不写成普遍推荐。",
    ),
}

NOTES = {
    "claim_hcc_ici_rechallenge": "第一轮：保留 contested；疗效增强与 irAE 增加并存，且无随机对照。写作时必须同时呈现疗效与安全性。",
    "claim_rt_immunomodulation_gap": "第一轮：保留 underdetermined；这是研究缺口陈述，不是疗效结论。",
    "claim_lenvatinib_vs_bev_uncertain": "第一轮：保留 underdetermined；仅一句“uncertain”，需补直接比较结果。",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    args = parser.parse_args()
    service.ensure_schema(args.db)
    conn = service.connect(args.db)
    try:
        applied = []
        for claim_id, (decision, note) in DECISIONS.items():
            claim = service.decide(conn, claim_id, decision, note, actor="round1")
            applied.append((claim_id, claim["status"], claim["decision"]))
        for claim_id, note in NOTES.items():
            claim = service.add_note(conn, claim_id, note, actor="round1")
            applied.append((claim_id, claim["status"], claim["decision"]))
        print({"applied": applied})
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
