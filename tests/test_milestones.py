"""Milestone collector parser tests (no network)."""

from __future__ import annotations

import unittest

from scripts.collect_milestones import PrRecord, parse_body, render

SAMPLE = """## 1. 背景描述

摘要通道没有提升 Recall。

## 2. 核心改动

新增 section prior。

## 3. 基准测试指标变化

| 指标 | 基线 | 变更后 | 变化 |
|---|---|---|---|
| Recall@10 | 0.5192 | 0.5192 | 0 |
| MRR | 0.3331 | 0.3597 | +8.0% |

### 测试

553 项通过。
"""


class MilestoneTests(unittest.TestCase):
    def test_parse(self) -> None:
        parsed = parse_body(SAMPLE)
        self.assertIn("摘要通道", parsed["background"])
        self.assertIn("section prior", parsed["changes"])
        self.assertEqual(len(parsed["metrics"]), 2)
        self.assertEqual(parsed["metrics"][0].metric, "Recall@10")
        self.assertEqual(parsed["missing_sections"], [])

    def test_missing(self) -> None:
        parsed = parse_body("## 1. 背景描述\n\n只有背景\n")
        self.assertIn("核心改动", parsed["missing_sections"])
        self.assertIn("基准测试指标变化", parsed["missing_sections"])

    def test_render(self) -> None:
        parsed = parse_body(SAMPLE)
        record = PrRecord(
            number=1,
            title="Test PR",
            merged_at="2026-10-28T00:00:00Z",
            url="https://example.test/pr/1",
            background=parsed["background"],
            changes=parsed["changes"],
            metrics=parsed["metrics"],
            tests=parsed["tests"],
        )
        text = render([record], "owner/repo")
        self.assertIn("# 项目里程碑数据表", text)
        self.assertIn("Recall@10", text)
        self.assertIn("PR #1", text)


if __name__ == "__main__":
    unittest.main()
