"""Protocol markdown rendering (no storage dependency)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def render_protocol_markdown(
    record: Dict[str, Any],
    runs: List[Dict[str, Any]],
    protocol_id: str = "",
) -> Optional[str]:
    if record is None:
        return None
    pid = protocol_id or record.get("protocol_id") or ""
    lines = [f"# {record.get('title') or pid}", ""]
    meta = []
    if record.get("doi"):
        meta.append(f"DOI: {record['doi']}")
    if record.get("version"):
        meta.append(f"版本: {record['version']}")
    if record.get("license"):
        meta.append(f"许可: {record['license']}")
    if record.get("url"):
        meta.append(f"来源: {record['url']}")
    if meta:
        lines.extend([" · ".join(meta), ""])
    lines.extend(["## 步骤", ""])
    steps = record.get("steps") or []
    if not steps:
        lines.extend(["（该协议没有解析出步骤）", ""])
    for step in steps:
        lines.append(f"### {step['ordinal']}. {step.get('title') or '(未命名步骤)'}")
        if step.get("duration"):
            lines.append(f"- 时长：{step['duration']}")
        if step.get("reagents"):
            lines.append(f"- 试剂：{'、'.join(step['reagents'])}")
        if step.get("instructions"):
            lines.extend(["", step["instructions"]])
        lines.append("")
    lines.extend(["## 实验记录", ""])
    if not runs:
        lines.append("（还没有实验记录）")
    else:
        lines.append("| 日期 | 标题 | 操作人 | 状态 | 步骤进度 | 结果 |")
        lines.append("|---|---|---|---|---|---|")
        for run in runs:
            done = len(run.get("done_steps") or [])
            lines.append(
                f"| {run.get('run_date') or ''} | {run.get('title') or ''} | "
                f"{run.get('operator') or ''} | {run.get('status') or ''} | "
                f"{done}/{len(steps)} | {(run.get('result') or '').replace('|', '/')} |"
            )
    lines.append("")
    return "\n".join(lines)
