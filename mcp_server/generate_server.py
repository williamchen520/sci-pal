"""SciPal MCP Server · generate —— 综述/大纲（只读 + 轮询壳，阶段五-B）。

serverName: `scipal-generate`　transport: stdio

⚠️ 本 server **不触发任何生成**。
    综述生成（`POST /api/review/generate`）、大纲生成（`/api/review/outline`）、
    多轮渐进式提问（`/api/agentic/search`）、问答（`/api/qa/ask`）、PDF 解析
    （`/api/papers/parse`）在 Flask 侧都是**同步阻塞**实现，耗时分钟级，远超 MCP
    的 60 秒 `toolCallTimeoutMs`，且没有 job 提交端点。
    → 这些能力要进 MCP，必须先做异步化（返回 job 句柄 + 独立 status 工具），
      属**业务代码改动**，规划在阶段五-C，需用户单独批准。

    因此本 server 只暴露「读已生成结果」与「查任务状态」这两类**快操作**。

设计铁律
    · 薄转发：只调 Flask 现有路由，不 import 任何 SciPal 内部模块，不加路由。
    · stdio 模式下 stdout 是 JSON-RPC 通道，本文件不向 stdout 打印。

工具（6 个）
    health / list_saved_outlines / get_saved_outline / get_review /
    paper_citation_graph / review_task_status
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from _forward import _call, _path_segment  # noqa: E402

SERVER_NAME = "scipal-generate"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SciPal 综述/大纲工具集（只读 + 轮询）。"
        "⚠️ 本 server 不触发任何生成动作：综述与大纲生成是同步长任务，"
        "MCP 侧尚无异步入口（规划于阶段五-C）。这里只能读取已生成的结果、"
        "查引用图谱、轮询已有任务状态。"
    ),
)


# ---------------------------------------------------------------------------
# 工具面（全部只读 / 快速，不触发 LLM）
# ---------------------------------------------------------------------------


@mcp.tool(description="SciPal 服务健康检查（GET /api/health）。无参数。")
def health() -> str:
    """检查 SciPal Flask API 是否在线（与 search 侧同名，但属不同 server）。"""
    return _call("GET", "/api/health")


@mcp.tool(description="列出已保存的大纲（GET /api/review/outline/saved），按更新时间倒序。")
def list_saved_outlines() -> str:
    """返回大纲名列表与数量。"""
    return _call("GET", "/api/review/outline/saved")


@mcp.tool(description="按名称读取已保存的大纲（GET /api/review/outline/saved/<name>）。")
def get_saved_outline(name: str) -> str:
    """读取指定大纲的完整记录；不存在返回 404。"""
    return _call("GET", f"/api/review/outline/saved/{_path_segment(name)}")


@mcp.tool(
    description=(
        "获取已生成综述的详情（GET /api/review/<review_id>），含 sentences 与 evidence_cards。"
        "⚠️ 只能读已存在的综述；本 server 不能生成综述。"
    )
)
def get_review(review_id: str) -> str:
    """按 review_id 读取综述；不存在或已过期返回 404。"""
    return _call("GET", f"/api/review/{_path_segment(review_id)}")


@mcp.tool(
    description=(
        "论文级引用图谱（GET /api/papers/<paper_id>/graph）：引用/被引/相似邻居。"
        "relation: cites|similar|all；direction: out|in|both；max_hops 1-3。"
    )
)
def paper_citation_graph(
    paper_id: str,
    relation: str = "all",
    direction: str = "both",
    max_hops: int = 1,
    max_total: int = 10,
) -> str:
    """从一篇论文出发做图遍历，返回邻居列表。"""
    hops = max(1, min(int(max_hops), 3))
    path = (
        f"/api/papers/{_path_segment(paper_id)}/graph"
        f"?relation={_path_segment(relation)}"
        f"&direction={_path_segment(direction)}"
        f"&max_hops={hops}"
        f"&max_total={int(max_total)}"
    )
    return _call("GET", path)


@mcp.tool(
    description=(
        "查询综述侧任务状态（GET /api/review/task/<task_id>）。"
        "注意：这是 review 的 TaskManager，与统一任务表 /api/tasks/<id> 不是同一套。"
    )
)
def review_task_status(task_id: str) -> str:
    """按 task_id 查询 review 任务（running/completed/failed/cancelled）。"""
    return _call("GET", f"/api/review/task/{_path_segment(task_id)}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
