"""SciPal MCP Server · generate —— 综述 / 大纲（阶段五-B，五-C C-1 增补异步大纲）。

serverName: `scipal-generate`　transport: stdio

能力边界（阶段五-C C-1 更新）
    ✅ **可提交**：大纲生成 `POST /api/review/outline` —— 自 V26.3 起就是**异步**的：
       服务端创建任务后**立即返回 `task_id`**（实测 ~0.13 s），用 `review_task_status` 轮询。
    ✅ **可取消**：`POST /api/review/cancel/<task_id>`。
    ❌ **不可提交**：综述正文生成 `POST /api/review/generate` 仍是**同步**实现
       （一次返回整篇 markdown，分钟级，无 task_id），异步化属阶段五-C 的 C-2，需用户单独批准。
    ❌ 同样不碰：`/api/agentic/search`、`/api/qa/ask`、`/api/papers/parse`（均为同步）。

两套任务体系，**不能混用**
    · 大纲/综述任务：进程内内存（`services/review/task_manager.py`），**不落库、重启即丢**
      → 只能查 `GET /api/review/task/<task_id>`；Flask 重启后旧 id 一律 404（不是 bug）。
    · 在线下载任务：SQLite `tasks` 表（持久）
      → 查 `GET /api/tasks/<task_id>`（由 `scipal-search` 的 `download_status` 使用）。

⚠️ Flask 是单线程（`app.run(threaded=False)`）：大纲任务运行期间 `/api/health` 实测会被
   饿到 20 s 以上，任务结束后立刻恢复。→ 轮询间隔建议 **≥5 s**，别秒级连打。

设计铁律
    · 薄转发：只调 Flask 现有路由，不 import 任何 SciPal 内部模块，不加路由。
    · stdio 模式下 stdout 是 JSON-RPC 通道，本文件不向 stdout 打印。

工具（8 个）
    health / list_saved_outlines / get_saved_outline / get_review /
    paper_citation_graph / review_task_status / generate_outline / cancel_review_task
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
        "SciPal 综述/大纲工具集（薄转发本地 Flask）。"
        "generate_outline 只负责提交任务并立即返回 task_id，"
        "必须用 review_task_status 轮询（建议间隔 >=5s）；"
        "task_id 存在 Flask 进程内存里，Flask 重启后失效并返回 404。"
        "综述正文生成（review/generate）仍是同步长任务，MCP 侧暂不支持。"
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


@mcp.tool(
    description=(
        "生成综述段落级大纲（POST /api/review/outline）。"
        "**立即返回 task_id，不要同步等待**；用 review_task_status 轮询，建议间隔 ≥5s。"
        "任务存在 Flask 进程内存里，Flask 重启后 task_id 会失效（返回 404）。"
        "review_type: narrative|comparative|systematic；language: en|zh。"
    )
)
def generate_outline(
    topic: str,
    max_papers: int = 20,
    review_type: str = "narrative",
    language: str = "en",
) -> str:
    """提交大纲生成任务，立即返回 {"task_id": ...}（异步，不等待结果）。"""
    # 参数名原样透传：Flask 侧读的就是 topic / max_papers / review_type / language
    return _call(
        "POST",
        "/api/review/outline",
        {
            "topic": topic,
            "max_papers": max_papers,
            "review_type": review_type,
            "language": language,
        },
    )


@mcp.tool(
    description=(
        "取消正在运行的综述/大纲任务（POST /api/review/cancel/<task_id>）。"
        "任务不存在或已结束 → 404（业务结果，不是故障）。"
    )
)
def cancel_review_task(task_id: str) -> str:
    """按 task_id 取消任务。"""
    return _call("POST", f"/api/review/cancel/{_path_segment(task_id)}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
