"""
Lightweight query router.
V21.4 - Query routing

Classifies a question into retrieval channels BEFORE searching, so we only
run the channels that are actually needed (faster, less noise).

Rule-based on purpose: instant, free, deterministic, debuggable.
Can later be replaced/augmented by an LLM classifier for hard cases.

Channels:
  - "qa":       paragraph hybrid search + rerank (default)
  - "figure":   figure caption search
  - "table":    table search
  - "citation": reference / bibliography lookup
  - "papers":   cross-paper literature discovery
"""
import re
from typing import Dict, List


# Keyword patterns (lowercased match). English + Chinese.
PATTERNS = {
    "figure": [
        r"\bfig(?:ure)?\.?\s*\d+\b", r"\bfig\b", r"\bfigure\b", r"\bplot\b",
        r"\bchart\b", r"\bdiagram\b", r"\bimage\b", r"\billustration\b",
        r"\bshown in\b", r"\bdepict", r"\bvisuali[sz]e\b",
        r"图\s*\d+", r"示意图", r"附图", r"图片", r"哪张图", r"图里", r"图中",
    ],
    "table": [
        r"\btable\s*\d+\b", r"\btable\b", r"\btab\.?\b", r"\bspreadsheet\b",
        r"表\s*\d+", r"表格", r"表里", r"表中", r"统计表",
    ],
    "citation": [
        r"\bref(?:erence)?s?\b", r"\bcit(?:e|ed|ation|ing)\b", r"\bbibliograph",
        r"\baccording to\b", r"\bwho (?:first |originally )?(?:proposed|found|reported|showed)\b",
        r"\bwhat (?:study|paper|article)\b", r"\bsource\b",
        r"参考文献", r"引用", r"引文", r"出处", r"谁(?:提出|发现|报道|研究|发表)",
        r"哪篇(?:论文|文献|文章)", r"根据.*研究",
    ],
    "papers": [
        r"\bwhich (?:papers?|studies|articles)\b", r"\bother (?:studies|papers|groups)\b",
        r"\bliterature\b", r"\breview\b", r"\bstate of the art\b",
        r"\bcompared? (?:across|between) (?:papers|studies)\b",
        r"\bhas anyone\b", r"\bwhat do we know about\b", r"\brelated work\b",
        r"哪些(?:论文|文献|研究|文章)", r"其他(?:研究|论文|团队|学者)",
        r"有没有(?:人|研究|论文)", r"综述", r"文献", r"研究现状", r"相关工作",
        r"对比.*(?:论文|研究)", r"不同(?:论文|研究)",
    ],
}

# Default channels always include paragraph QA as a fallback signal.
CHANNEL_WEIGHTS = {
    "figure": 3,
    "table": 3,
    "citation": 2,
    "papers": 2,
}


class QueryRouter:
    def route(self, query: str, paper_id: str = None) -> Dict:
        """
        Decide which retrieval channels to run.

        Returns:
          {
            "primary": str,          # dominant intent
            "channels": [str, ...],  # channels to actually run
            "scores": {channel: n},  # matched-pattern counts
            "scoped_to_paper": bool, # inside one paper -> no cross-paper search
          }
        """
        q = query.lower()
        scores: Dict[str, int] = {}

        for channel, patterns in PATTERNS.items():
            hits = 0
            for pat in patterns:
                if re.search(pat, q):
                    hits += 1
            if hits:
                scores[channel] = hits * CHANNEL_WEIGHTS.get(channel, 1)

        # Primary intent = highest score; default to qa.
        primary = max(scores, key=scores.get) if scores else "qa"

        # Build active channel set. QA always runs (cheap, catches the answer).
        channels: List[str] = ["qa"]
        for ch in ("figure", "table", "citation", "papers"):
            if ch in scores:
                channels.append(ch)

        # Cross-paper discovery only makes sense outside a single paper.
        scoped = paper_id is not None
        if scoped and "papers" in channels:
            channels.remove("papers")

        return {
            "primary": primary,
            "channels": channels,
            "scores": scores,
            "scoped_to_paper": scoped,
        }


if __name__ == "__main__":
    router = QueryRouter()
    tests = [
        "How does STAT1 regulate the interferon response?",
        "What does Figure 3 show about TNNT1?",
        "图7里画的是什么？",
        "Give me the table of patient demographics",
        "Which papers first reported STAT1 gain-of-function mutations?",
        "有没有其他研究做过单细胞质谱的基准测试？",
        "According to which study was CyTOF first applied to PBMCs?",
        "总结一下这篇论文的方法",
    ]
    print("=" * 60)
    print("🧭 Query Router Test")
    print("=" * 60)
    for t in tests:
        r = router.route(t)
        print(f"\nQ: {t}")
        print(f"   primary={r['primary']}  channels={r['channels']}  scores={r['scores']}")
