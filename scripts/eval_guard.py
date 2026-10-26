"""scipal-guard 质量评估：三个场景，人工可复现。

    python scripts/eval_guard.py

场景 A：真实综述片段（期望 unknown 0）
场景 B：掺入 3 个编造基因（期望 unknown 3）
场景 C：方法/技术密集（期望 0 误报，CRISPR 落 corpus）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.quality.guard import FtsLanding, VocabularyGuard  # noqa: E402

SCENARIOS = {
    "A_clean": (
        "Sepsis is driven by TLR4 and NLRP3 signaling in macrophages, and EGFR "
        "transactivation amplifies the inflammatory response. STAT3 phosphorylation "
        "was validated in murine models of chronic infection.",
        {"unknown": 0},
    ),
    "B_fabricated": (
        "Sepsis is driven by TLR4 and NLRP3 signaling in macrophages. Treatment with "
        "FOOBARZ9 and XYZQ1 reduced cytokine release, while ZZZZ8 had no effect.",
        {"unknown": 3},
    ),
    "C_methods": (
        "We used CRISPR knockout, Western blot, qPCR and flow cytometry to validate "
        "STAT3 phosphorylation after TLR4 stimulation.",
        {"unknown": 0},
    ),
}


def main() -> int:
    landing = FtsLanding()
    guard = VocabularyGuard(fts_lookup=landing)
    failures = 0
    for name, (text, expected) in SCENARIOS.items():
        report = guard.check(text)
        summary = report.summary()
        ok = all(summary.get(key) == value for key, value in expected.items())
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: checked={summary['checked']} "
              f"unknown={summary['unknown']} ratio={summary['unknown_ratio']:.2f} "
              f"counts={json.dumps(summary['counts'], ensure_ascii=False)}")
        for issue in summary["issues"]:
            if issue["status"] in {"unknown", "undefined_abbrev"}:
                print(f"    - {issue['term']}: {issue['status']}")
    landing.close()
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
