"""Collect benchmark data from merged GitHub PRs into a Markdown milestone table.

Usage:
    python scripts/collect_milestones.py --repo williamchen520/sci-pal
    python scripts/collect_milestones.py --token $env:GITHUB_TOKEN

Token resolution:
1. --token
2. GITHUB_TOKEN / GH_TOKEN
3. git credential fill (github.com)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_REPO = "williamchen520/sci-pal"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "项目里程碑数据表.md"

SECTION_BACKGROUND = re.compile(
    r"^##\s*(?:(?:1|一)\.?\s*)?(?:背景描述|背景|说明)\s*$", re.MULTILINE
)
SECTION_CHANGES = re.compile(
    r"^##\s*(?:(?:2|二)\.?\s*)?(?:核心改动|改动|内容|主要改动)\s*$", re.MULTILINE
)
SECTION_BENCH = re.compile(
    r"^##\s*(?:3\.\s*)?基准测试[^\n]*$", re.MULTILINE
)
SECTION_TESTS = re.compile(r"^###\s*测试[^\n]*$", re.MULTILINE)


@dataclass
class MetricRow:
    metric: str
    baseline: str
    after: str
    change: str


@dataclass
class PrRecord:
    number: int
    title: str
    merged_at: str
    url: str
    background: str = ""
    changes: str = ""
    metrics: List[MetricRow] = field(default_factory=list)
    tests: str = ""
    missing_sections: List[str] = field(default_factory=list)


def _section(text: str, pattern: re.Pattern) -> str:
    match = pattern.search(text or "")
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _clean(text: str, limit: int = 400) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    return value[:limit]


def parse_body(body: str) -> Dict:
    body = body or ""
    background = _section(body, SECTION_BACKGROUND)
    changes = _section(body, SECTION_CHANGES)
    bench = _section(body, SECTION_BENCH)
    tests_section = _section(bench, SECTION_TESTS) if bench else ""
    if not tests_section:
        tests_match = SECTION_TESTS.search(body)
        if tests_match:
            tests_section = body[tests_match.end() :].strip()

    metrics: List[MetricRow] = []
    table_source = bench if bench else body
    metric_name = re.compile(r"recall|mrr|ndcg|refusal|precision|f1|accuracy", re.IGNORECASE)
    for line in table_source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        if cells[0].lower() in ("指标", "metric", "metrics"):
            continue
        if not metric_name.search(cells[0]):
            continue
        metrics.append(
            MetricRow(
                metric=cells[0],
                baseline=cells[1] if len(cells) > 1 else "",
                after=cells[2] if len(cells) > 2 else "",
                change=cells[3] if len(cells) > 3 else "",
            )
        )

    seen_metrics = {metric.metric.lower() for metric in metrics}
    inline = re.compile(
        r"(Recall@10|recall@10|MRR|mrr|nDCG@10|ndcg@10|refusal_accuracy)"
        r"\s*[:=]\s*([0-9.]+)(?:\s*(?:→|->|to)\s*([0-9.]+))?"
    )
    for match in inline.finditer(body or ""):
        name = match.group(1)
        if name.lower() in seen_metrics:
            continue
        baseline = match.group(2) or ""
        after = match.group(3) or baseline
        metrics.append(
            MetricRow(
                metric=name,
                baseline=baseline if match.group(3) else "",
                after=after,
                change="",
            )
        )
        seen_metrics.add(name.lower())

    missing = []
    if not background:
        missing.append("背景描述")
    if not changes:
        missing.append("核心改动")
    if not bench or not metrics:
        missing.append("基准测试指标变化")
    return {
        "background": background,
        "changes": changes,
        "metrics": metrics,
        "tests": tests_section,
        "missing_sections": missing,
    }


def get_token(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:  # noqa: BLE001
        pass
    return ""


def api_get(url: str, token: str) -> object:
    headers = {"User-Agent": "SciPal-Milestones", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_merged_prs(repo: str, token: str, max_pages: int = 20) -> List[PrRecord]:
    records: List[PrRecord] = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=100&page={page}"
        payload = api_get(url, token)
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if not item.get("merged_at"):
                continue
            parsed = parse_body(item.get("body") or "")
            records.append(
                PrRecord(
                    number=item["number"],
                    title=item.get("title") or "",
                    merged_at=item.get("merged_at") or "",
                    url=item.get("html_url") or "",
                    background=parsed["background"],
                    changes=parsed["changes"],
                    metrics=parsed["metrics"],
                    tests=parsed["tests"],
                    missing_sections=parsed["missing_sections"],
                )
            )
        if len(payload) < 100:
            break
    records.sort(key=lambda record: record.number)
    return records


def _escape(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def render(records: List[PrRecord], repo: str = DEFAULT_REPO) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 项目里程碑数据表",
        "",
        f"> 自动生成，请勿手工编辑；生成时间：{generated}",
        f"> 仓库：`{repo}`；数据来源：已合并 PR 的“基准测试指标变化”章节。",
        "> 评测语料：本地论文库全部文章（当前 3,297 篇）。",
        "> 重生成：`python scripts/collect_milestones.py`",
        "",
        "## 1. PR 总览",
        "",
        "| PR | 标题 | 合并时间 | 指标数 | 模板 |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        status = "完整" if not record.missing_sections else "缺少：" + "、".join(record.missing_sections)
        lines.append(
            f"| [#{record.number}]({record.url}) | {_escape(record.title)} | "
            f"{record.merged_at[:10]} | {len(record.metrics)} | {_escape(status)} |"
        )

    lines += ["", "## 2. 指标明细", "", "| PR | 指标 | 基线 | 变更后 | 变化 |", "|---|---|---|---|---|"]
    for record in records:
        for metric in record.metrics:
            lines.append(
                f"| #{record.number} | {_escape(metric.metric)} | "
                f"{_escape(metric.baseline)} | {_escape(metric.after)} | {_escape(metric.change)} |"
            )

    lines += ["", "## 3. PR 详情", ""]
    for record in records:
        lines.append(f"### PR #{record.number} · {record.title}")
        lines.append("")
        lines.append(f"- 合并时间：{record.merged_at[:10]}")
        lines.append(f"- 链接：{record.url}")
        lines.append(f"- 背景：{_clean(record.background) or '（未填写）'}")
        lines.append(f"- 核心改动：{_clean(record.changes) or '（未填写）'}")
        if record.tests:
            lines.append(f"- 测试：{_clean(record.tests)}")
        if record.metrics:
            lines += ["", "| 指标 | 基线 | 变更后 | 变化 |", "|---|---|---|---|"]
            for metric in record.metrics:
                lines.append(
                    f"| {_escape(metric.metric)} | {_escape(metric.baseline)} | "
                    f"{_escape(metric.after)} | {_escape(metric.change)} |"
                )
        if record.missing_sections:
            lines.append("")
            lines.append(f"> 警告：缺少 {', '.join(record.missing_sections)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--token", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()

    token = get_token(args.token)
    records = list_merged_prs(args.repo, token, args.max_pages)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(records, args.repo), encoding="utf-8")
    print(f"wrote {len(records)} merged PRs -> {output}")


if __name__ == "__main__":
    main()
