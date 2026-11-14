"""Deterministic replication plan from module map + data flow."""

from __future__ import annotations

from typing import Any

from services.papers.flow import paper_data_flow
from services.papers.modules import paper_modules


def replication_plan(paper_id: str, target: str) -> dict[str, Any]:
    target = (target or "").strip()
    if not target:
        raise ValueError("target is required")
    modules = paper_modules(paper_id)
    if modules.get("status") == "unbound":
        return {
            "paper_id": paper_id,
            "target": target,
            "status": "blocked",
            "reason": "no code library binding",
            "steps": [],
            "tests": [],
        }
    module = next(
        (
            item
            for item in modules.get("modules", [])
            if target == item.get("path") or target == item.get("path", "").split("/")[-1]
        ),
        None,
    )
    if not module:
        return {
            "paper_id": paper_id,
            "target": target,
            "status": "blocked",
            "reason": "target module not found",
            "steps": [],
            "tests": [],
        }
    flow = paper_data_flow(paper_id)
    source = f"file:{module['path']}"
    reads = [
        edge["target"].removeprefix("artifact:")
        for edge in flow.get("edges", [])
        if edge.get("source") == source and edge.get("relation") == "reads"
    ]
    writes = [
        edge["target"].removeprefix("artifact:")
        for edge in flow.get("edges", [])
        if edge.get("source") == source and edge.get("relation") == "writes"
    ]
    return {
        "paper_id": paper_id,
        "target": module["path"],
        "status": "planned",
        "language": module.get("language", ""),
        "inputs": reads,
        "outputs": writes,
        "steps": [
            f"确认输入存在：{', '.join(reads) if reads else '(none declared)'}",
            f"在隔离环境打开 {module['path']}",
            "按论文/README 固定运行参数",
            f"运行 {module['path']}",
            f"对比输出：{', '.join(writes) if writes else '(none declared)'}",
        ],
        "tests": [],
        "risks": [
            "仓库无 LICENSE 或未记录运行环境",
            "输入数据未随仓库提供",
            "只做静态计划，未执行",
        ],
        "executed": False,
    }
