"""Risk-of-bias summary chart (SVG)."""

from __future__ import annotations

from collections import Counter
from html import escape
from typing import Dict, List

COLORS = {"low": "#22c55e", "some concerns": "#f59e0b", "high": "#ef4444"}
LABELS = {"low": "Low", "some concerns": "Some", "high": "High"}
DOMAINS = ["randomization", "deviations", "missing_data", "measurement", "reporting"]


def _counts(rows: List[Dict]) -> Dict[str, Counter]:
    out = {domain: Counter() for domain in DOMAINS}
    for row in rows:
        domain = row.get("domain")
        if domain in out:
            out[domain][row.get("judgement", "some concerns")] += 1
    return out


def render(rows: List[Dict], width: int = 760, height: int = 320) -> str:
    counts = _counts(rows)
    total = max(1, len(rows))
    bar_width = 380
    left = 200
    top = 70
    gap = 42
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="30" y="36" fill="#0f172a" font-size="20" font-family="Microsoft YaHei, sans-serif">'
        "Risk of bias by domain</text>",
    ]
    for index, domain in enumerate(DOMAINS):
        y = top + index * gap
        parts.append(
            f'<text x="30" y="{y + 16}" fill="#334155" font-size="14" '
            f'font-family="Microsoft YaHei, sans-serif">{escape(domain)}</text>'
        )
        x = left
        for judgement in ("low", "some concerns", "high"):
            count = counts[domain].get(judgement, 0)
            if not count:
                continue
            segment = max(4, int(bar_width * count / total))
            parts.append(
                f'<rect x="{x}" y="{y}" width="{segment}" height="22" fill="{COLORS[judgement]}"/>'
            )
            if segment > 28:
                parts.append(
                    f'<text x="{x + segment / 2}" y="{y + 16}" fill="#ffffff" font-size="12" '
                    f'text-anchor="middle" font-family="Microsoft YaHei, sans-serif">{count}</text>'
                )
            x += segment
    legend = [
        (f"Low", COLORS["low"]),
        ("Some concerns", COLORS["some concerns"]),
        ("High", COLORS["high"]),
    ]
    for i, (label, color) in enumerate(legend):
        x = 30 + i * 160
        parts.append(f'<rect x="{x}" y="{height - 40}" width="14" height="14" fill="{color}"/>')
        parts.append(
            f'<text x="{x + 22}" y="{height - 28}" fill="#334155" font-size="13" '
            f'font-family="Microsoft YaHei, sans-serif">{escape(label)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
