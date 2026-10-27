"""SciPal MCP Server · data —— 本地数据沙箱（scipal-data）。

薄转发 `/api/data/*`：原始文件只在本机处理，云端只允许拿到
经 `cloud-gate` 校验的聚合/脱敏产物。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from _forward import _call, _path_segment  # noqa: E402

SERVER_NAME = "scipal-data"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "本地数据沙箱工具：只处理本机 xlsx/csv/tsv/docx，"
        "返回聚合统计与脱敏样例；原始行不得上传云端。"
        "云端分析前必须调用 cloud_gate，allow=true 才可发送产物。"
    ),
)


@mcp.tool(description="数据分级（GET /api/data/classify）：raw / public，并返回会话策略。")
def data_classify(path: str) -> str:
    return _call("GET", f"/api/data/classify?path={_path_segment(path)}")


@mcp.tool(
    description=(
        "生成数据画像（POST /api/data/profile）：列类型、缺失、唯一值、"
        "Top 值（n<10 抑制）与脱敏样例。返回 profile/sample artifact_id。"
    )
)
def data_profile(path: str, project_id: str, sheet: str = "") -> str:
    return _call(
        "POST",
        "/api/data/profile",
        {"path": path, "project_id": project_id, "sheet": sheet},
    )


@mcp.tool(
    description=(
        "本地分组聚合（POST /api/data/aggregate）：按 group_by 分组，"
        "n<10 的组被抑制；可选 metrics 均值。"
    )
)
def data_aggregate(
    path: str,
    project_id: str,
    group_by: list[str],
    metrics: list[str] | None = None,
) -> str:
    return _call(
        "POST",
        "/api/data/aggregate",
        {
            "path": path,
            "project_id": project_id,
            "group_by": group_by,
            "metrics": metrics or [],
        },
    )


@mcp.tool(description="生成脱敏样例（POST /api/data/sample）：最多 5 行，敏感列自动剔除。")
def data_sample(path: str, project_id: str, sheet: str = "") -> str:
    return _call(
        "POST",
        "/api/data/sample",
        {"path": path, "project_id": project_id, "sheet": sheet},
    )


@mcp.tool(description="列出项目产物（GET /api/data/artifacts）。")
def artifact_list(project_id: str) -> str:
    return _call("GET", f"/api/data/artifacts?project_id={_path_segment(project_id)}")


@mcp.tool(description="读取产物内容（GET /api/data/artifacts/<id>）。")
def artifact_read(artifact_id: str, project_id: str) -> str:
    return _call(
        "GET",
        f"/api/data/artifacts/{_path_segment(artifact_id)}?project_id={_path_segment(project_id)}",
    )


@mcp.tool(
    description=(
        "人工修正产物（PUT /api/data/artifacts/<id>）：生成新版本，"
        "旧版本保留；修正后必须 validate。"
    )
)
def artifact_update(artifact_id: str, project_id: str, content: str) -> str:
    return _call(
        "PUT",
        f"/api/data/artifacts/{_path_segment(artifact_id)}",
        {"project_id": project_id, "content": content},
    )


@mcp.tool(description="校验产物（POST /api/data/artifacts/<id>/validate）：n≥10、列白名单、样例行数。")
def artifact_validate(artifact_id: str, project_id: str) -> str:
    return _call(
        "POST",
        f"/api/data/artifacts/{_path_segment(artifact_id)}/validate",
        {"project_id": project_id},
    )


@mcp.tool(
    description=(
        "云端出口检查（POST /api/data/cloud-gate）：allow=true 才允许把产物交给云端模型。"
    )
)
def cloud_gate(artifact_id: str, project_id: str) -> str:
    return _call(
        "POST",
        "/api/data/cloud-gate",
        {"artifact_id": artifact_id, "project_id": project_id},
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
