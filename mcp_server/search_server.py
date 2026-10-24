"""SciPal MCP Server · search —— 文献检索 / 下载（阶段五-B）。

serverName: `scipal-search`　transport: stdio

职责边界（按科研业务流切分）
    本 server 只负责「找文献、拿文献、下载文献」：本地混合检索、在线检索、
    论文详情、启动下载任务、查询下载进度。

设计铁律
    · 薄转发：只调 Flask 现有路由，**不 import 任何 SciPal 内部模块**，不加路由、不改业务代码。
    · 不承载模型：embedding / reranker / ChromaDB 全在常驻的 Flask 进程里。
    · stdio 模式下 stdout 是 JSON-RPC 通道，本文件不向 stdout 打印。

工具（6 个，有意设上限 —— 真正的约束是模型上下文，不是显存）
    health / search_hybrid / search_online / get_paper /
    download_online_papers / download_status

参数名以 api_server.py 路由实际读取的为准：
    /api/search/hybrid  读 `q`（不是 query），`use_online` 服务端默认 true —— 本工具默认 false
    /api/search/online  读 `q` / `max_results` / `search_pubmed` / `search_pmc`
    /api/search/download_online  读 `pmc_ids`，**立即返回 task_id**（异步）
"""

from __future__ import annotations

import sys
from pathlib import Path

# 公共薄转发层与本文件同目录；用 __file__ 推导，避免 cwd 变化导致 import 失败
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from _forward import _call, _path_segment  # noqa: E402

SERVER_NAME = "scipal-search"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SciPal 文献检索与下载工具（薄转发本地 Flask API）。"
        "检索/详情是同步只读调用；下载由 download_online_papers 立即返回 task_id，"
        "必须用 download_status 轮询，不要同步等待。"
    ),
)


# ---------------------------------------------------------------------------
# 工具面
# ---------------------------------------------------------------------------


@mcp.tool(description="SciPal 服务健康检查（GET /api/health）。无参数。")
def health() -> str:
    """检查 SciPal Flask API 是否在线。"""
    return _call("GET", "/api/health")


@mcp.tool(
    description=(
        "混合检索论文（POST /api/search/hybrid）：本地库 + 可选在线 NCBI。"
        "use_online 默认 false（服务端默认 true 会联网，容易超过 MCP 60 秒上限）；"
        "需要在线检索时显式传 true。"
    )
)
def search_hybrid(query: str, top_k: int = 10, use_online: bool = False) -> str:
    """按关键词在本地库（可选叠加在线）混合检索。"""
    return _call(
        "POST",
        "/api/search/hybrid",
        {"q": query, "top_k": top_k, "use_online": use_online},
    )


@mcp.tool(
    description=(
        "仅在线检索 NCBI PubMed/PMC（POST /api/search/online），不搜本地库。"
        "max_results 每个库默认 20（联网较慢，不建议调大）。"
    )
)
def search_online(
    query: str,
    max_results: int = 20,
    search_pubmed: bool = True,
    search_pmc: bool = True,
) -> str:
    """在线检索 NCBI，返回 pubmed / pmc 命中列表。"""
    return _call(
        "POST",
        "/api/search/online",
        {
            "q": query,
            "max_results": max_results,
            "search_pubmed": search_pubmed,
            "search_pmc": search_pmc,
        },
    )


@mcp.tool(
    description="获取单篇论文详情（GET /api/papers/<paper_id>）：元数据 + 引用/被引/相似。"
)
def get_paper(paper_id: str) -> str:
    """按 paper_id 查询论文详情。"""
    return _call("GET", f"/api/papers/{_path_segment(paper_id)}")


@mcp.tool(
    description=(
        "启动在线文献下载任务（POST /api/search/download_online），入参为 PMCID 列表。"
        "**立即返回 task_id（异步）**，必须用 download_status 轮询进度，不要同步等待。"
    )
)
def download_online_papers(pmc_ids: list[str]) -> str:
    """提交 PMCID 列表，后台执行下载→入库→建索引。"""
    return _call("POST", "/api/search/download_online", {"pmc_ids": pmc_ids})


@mcp.tool(
    description="查询在线下载任务进度（GET /api/search/download_status?task_id=...）。"
)
def download_status(task_id: str) -> str:
    """按 task_id 轮询下载阶段（downloading / importing / indexing / completed）。"""
    return _call(
        "GET",
        f"/api/search/download_status?task_id={_path_segment(task_id)}",
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
