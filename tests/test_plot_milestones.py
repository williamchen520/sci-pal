"""Milestone chart data loader tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.plot_milestones import load_metric_rows

TABLE = """# Table

## 2. 指标明细

| PR | 指标 | 基线 | 变更后 | 变化 |
|---|---|---|---|---|
| #1 | Recall@10 | 0.5 | 0.6 | +20% |
| #2 | MRR | 0.3 | 0.35 | +16% |
| #3 | Recall@10 |  | 0.65 |  |

## 3. 详情
"""


class PlotTests(unittest.TestCase):
    def test_load(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "table.md"
            path.write_text(TABLE, encoding="utf-8")
            rows = load_metric_rows(path, "Recall@10")
        self.assertEqual(rows, [(1, 0.6, 0.5), (3, 0.65, None)])


if __name__ == "__main__":
    unittest.main()
