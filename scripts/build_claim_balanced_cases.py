#!/usr/bin/env python3
"""Build a balanced, *derived* claim-verifier benchmark.

This is not a new clinical claim set. It creates three cases per pilot claim:

1. support: original claim + its curated support quote;
2. refute: an explicitly negated claim + the same quote (derived opposition);
3. underdetermine: original claim + a boundary/method quote.

The derived refute cases must be human-reviewed before publication. The script
exists so the benchmark is reproducible, not so the labels become gold by
construction.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLAIMS = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claims_pilot.yaml"
DEFAULT_DB = ROOT / "data" / "research.db"
DEFAULT_OUT = ROOT / "eval" / "plugins" / "claims_pilot_balanced_cases.json"

OPPOSITE = {
    "claim_hcc_triple_os": "在不可切除肝细胞癌中，TACE 联合抗 VEGF/TKI 与 PD-1/PD-L1 的方案，较 TACE 单药或其他对照方案并不提高总生存。",
    "claim_hcc_dtace_haic": "对大肝癌合并下腔静脉和/或右心房癌栓患者，dTACE 联合 HAIC、分子靶向治疗与 PD-1 抑制剂，并不优于不含 dTACE 的同类方案。",
    "claim_hcc_ici_rechallenge": "对部分 HCC 患者，免疫检查点抑制剂再挑战不会增强抗肿瘤反应。",
    "claim_hdv_hcc_signature": "HDV 相关 HCC 与 HBV 相关 HCC 具有相同的全身炎症介质谱。",
    "claim_tcsp_prognosis": "基于单细胞 CD8+ T 细胞状态构建的 TCSP 评分越高，HCC 患者总生存越长。",
    "claim_hcc_time_immunosuppressive": "HCC 的肿瘤免疫微环境并非深度免疫抑制。",
    "claim_fabp5_immune": "在 HCC 中，FABP5 高表达与 CD8+ T 细胞和巨噬细胞等免疫细胞浸润减少相关。",
    "claim_rt_immunomodulation_gap": "放疗对 HCC 肿瘤免疫微环境的作用已从机制假设转化为稳健临床获益。",
    "claim_lenvatinib_vs_bev_uncertain": "对 HCC 合并大血管侵犯患者，lenvatinib 为基础与 bevacizumab 为基础的三联方案孰优，已有明确一致证据。",
    "claim_sbrt_ici_watch": "在部分不可切除 HCC 中，SBRT 后接受 PD-1/PD-L1 治疗并达到完全缓解者，不应暂停免疫治疗。",
}

UNDERDETERMINE_IDS = [
    "paper_PMC13399579_937f5057_xml_para_00013_sent_002",
    "paper_PMC13615806_d62ab6f2_xml_para_00035_sent_001",
    "para_paper_PMC12707946_2d3bcc67_0008_sent_002",
    "para_paper_PMC12707946_2d3bcc67_0063_sent_002",
    "paper_PMC13399579_937f5057_xml_para_00091_sent_007",
]


def _quote(conn: sqlite3.Connection, sentence_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT text, paper_id FROM sentences WHERE sentence_id = ?", (sentence_id,)
    ).fetchone()
    if not row:
        raise SystemExit(f"missing sentence: {sentence_id}")
    return row[0], row[1]


def build(claims_path: Path, db_path: Path, out_path: Path) -> dict:
    data = yaml.safe_load(claims_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cases = []
    try:
        for index, claim in enumerate(data.get("claims") or []):
            supports = [
                item
                for item in claim.get("evidence") or []
                if item.get("relation") == "supports"
            ]
            if not supports:
                continue
            item = supports[0]
            quote, paper_id = _quote(conn, item["sentence_id"])
            base = {
                "claim_id": claim["claim_id"],
                "qualifiers": claim.get("qualifiers") or {},
            }
            cases.append(
                {
                    "case_id": f"{claim['claim_id']}__support",
                    "claim": {**base, "text": claim["claim_text"]},
                    "evidence": [
                        {
                            "evidence_id": item["sentence_id"],
                            "paper_id": paper_id,
                            "quote": quote,
                            "gold_relation": "supports",
                        }
                    ],
                    "provenance": "pilot_support",
                }
            )
            cases.append(
                {
                    "case_id": f"{claim['claim_id']}__refute",
                    "claim": {**base, "text": OPPOSITE[claim["claim_id"]]},
                    "evidence": [
                        {
                            "evidence_id": item["sentence_id"],
                            "paper_id": paper_id,
                            "quote": quote,
                            "gold_relation": "refutes",
                        }
                    ],
                    "provenance": "derived_opposite_claim",
                }
            )
            under_id = UNDERDETERMINE_IDS[index % len(UNDERDETERMINE_IDS)]
            under_text, under_paper = _quote(conn, under_id)
            cases.append(
                {
                    "case_id": f"{claim['claim_id']}__underdetermine",
                    "claim": {**base, "text": claim["claim_text"]},
                    "evidence": [
                        {
                            "evidence_id": under_id,
                            "paper_id": under_paper,
                            "quote": under_text,
                            "gold_relation": "underdetermines",
                        }
                    ],
                    "provenance": "manual_boundary",
                }
            )
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = {
        relation: sum(
            1 for case in cases if case["evidence"][0]["gold_relation"] == relation
        )
        for relation in ("supports", "refutes", "underdetermines")
    }
    return {"cases": len(cases), **counts, "out": str(out_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    print(build(Path(args.claims), Path(args.db), Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
