"""Plot a metric from the auto-generated milestone table.

Usage:
    python scripts/plot_milestones.py --metric Recall@10 --output docs/milestones_recall.svg
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_TABLE = Path(__file__).resolve().parent.parent / "docs" / "项目里程碑数据表.md"


def load_metric_rows(table_path: Path, metric: str) -> List[Tuple[int, float, float | None]]:
    text = table_path.read_text(encoding="utf-8")
    in_metrics = False
    rows: Dict[int, Tuple[float, float | None]] = {}
    for line in text.splitlines():
        if line.startswith("## 2."):
            in_metrics = True
            continue
        if in_metrics and line.startswith("## "):
            break
        if not in_metrics or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        pr_match = re.search(r"#(\d+)", cells[0])
        if not pr_match:
            continue
        if cells[1].lower() != metric.lower():
            continue
        try:
            after = float(cells[3])
        except ValueError:
            continue
        try:
            baseline = float(cells[2]) if cells[2] else None
        except ValueError:
            baseline = None
        pr = int(pr_match.group(1))
        rows[pr] = (after, baseline)
    return [(pr, after, baseline) for pr, (after, baseline) in sorted(rows.items())]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=str(DEFAULT_TABLE))
    parser.add_argument("--metric", default="Recall@10")
    parser.add_argument("--output", default="docs/milestones_recall.svg")
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = load_metric_rows(Path(args.table), args.metric)
    if not rows:
        raise SystemExit(f"no rows for metric: {args.metric}")

    prs = [row[0] for row in rows]
    after = [row[1] for row in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(prs, after, marker="o", linewidth=2, label=f"{args.metric} (after)")
    baseline_points = [(row[0], row[2]) for row in rows if row[2] is not None]
    if baseline_points:
        ax.scatter(
            [point[0] for point in baseline_points],
            [point[1] for point in baseline_points],
            marker="x",
            label=f"{args.metric} (baseline)",
        )
    for pr, value, _ in rows:
        ax.annotate(str(value), (pr, value), textcoords="offset points", xytext=(0, 8), fontsize=8)
    ax.set_xlabel("Merged PR #")
    ax.set_ylabel(args.metric)
    ax.set_title(f"{args.metric} across merged PRs")
    ax.grid(True, alpha=0.3)
    ax.legend()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output)
    print(f"wrote {output} ({len(rows)} points)")


if __name__ == "__main__":
    main()
