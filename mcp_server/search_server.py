"""SciPal MCP Server · search —— 文献检索 / 下载（阶段五-B）。

serverName: `scipal-search`　transport: stdio

职责边界（按科研业务流切分）
    本 server 只负责「找文献、拿文献、下载文献」：本地混合检索、在线检索、
    论文详情、启动下载任务、查询下载进度。

设计铁律
    · 薄转发：只调 Flask 现有路由，**不 import 任何 SciPal 内部模块**，不加路由、不改业务代码。
    · 不承载模型：embedding / reranker / ChromaDB 全在常驻的 Flask 进程里。
    · stdio 模式下 stdout 是 JSON-RPC 通道，本文件不向 stdout 打印。

工具（10 个 —— 真正的约束是模型上下文，不是显存）
    health / search_hybrid / search_online / get_paper /
    download_online_papers / download_status /
    ask_question / agentic_search /
    list_local_papers / parse_paper

参数名以 api_server.py 路由实际读取的为准：
    /api/search/hybrid  读 `q`（不是 query），`use_online` 服务端默认 true —— 本工具默认 false
    /api/search/online  读 `q` / `max_results` / `search_pubmed` / `search_pmc`
    /api/search/download_online  读 `pmc_ids`，**立即返回 task_id**（异步）
"""

from __future__ import annotations

import json
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
        "SciPal 文献检索、下载与问答工具（薄转发本地 Flask API）。"
        "检索/详情是同步只读调用；"
        "download_online_papers / ask_question / agentic_search 都**立即返回 task_id**，"
        "必须用 review_task_status 轮询（同一套 task_manager），不要同步等待。"
        "任务存在 Flask 进程内存里，Flask 重启即丢。"
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


@mcp.tool(
    description=(
        "提交学术问答任务（POST /api/qa/ask_async）：检索证据 → LLM 生成 → 引用覆盖率校验。"
        "**立即返回 task_id，不要同步等待**（实测单次 >120 s）；"
        "用 review_task_status 轮询，建议间隔 ≥5 s。"
        "任务存在 Flask 进程内存里，Flask 重启即丢（会 404）。"
        "取消只在提交前 / 返回后生效，ask() 内部不可中断。"
    )
)
def ask_question(question: str, paper_id: str = "", diagnostics: bool = False) -> str:
    """提交问答任务，立即返回 {"task_id": ...}。"""
    payload = {"question": question, "diagnostics": diagnostics}
    if paper_id.strip():
        payload["paper_id"] = paper_id.strip()
    return _call("POST", "/api/qa/ask_async", payload)


@mcp.tool(
    description=(
        "提交多跳（agentic）检索任务（POST /api/agentic/search_async）："
        "逐跳检索 + 实体覆盖度判断，直到达到 max_hops 或 min_coverage。"
        "**立即返回 task_id，不要同步等待**（max_hops=1 实测也要数十秒）；"
        "用 review_task_status 轮询，建议间隔 ≥5 s。"
        "max_hops 钳制在 1–5。任务存在 Flask 进程内存里，重启即丢。"
    )
)
def agentic_search(
    query: str,
    max_hops: int = 3,
    min_coverage: float = 0.6,
    top_paragraphs: int = 6,
    paper_id: str = "",
) -> str:
    """提交多跳检索任务，立即返回 {"task_id": ...}。"""
    payload = {
        "q": query,
        "max_hops": max(1, min(int(max_hops), 5)),
        "min_coverage": float(min_coverage),
        "top_paragraphs": int(top_paragraphs),
    }
    if paper_id.strip():
        payload["paper_id"] = paper_id.strip()
    return _call("POST", "/api/agentic/search_async", payload)


@mcp.tool(
    description=(
        "列出 documents/ 目录下的本地 PDF 及其入库状态（GET /api/papers/local）。"
        "默认只返回精简字段（filename/parsed/paper_id/title/file_size_mb/paragraph_count），"
        "避免 70+ 篇全量灌进上下文；only_unparsed=true 只看未解析的；"
        "limit 默认 20、**上限 50**（超出按 50 截断），"
        "超出会在结果里标注「已截断，共 N 篇」。"
        "⚠️ 只能看**已有** PDF，本工具不能上传文件。"
        "⚠️ documents 目录不存在时返回 {\"ok\": false, \"error\": ...}，不是「0 篇」。"
    )
)
def list_local_papers(only_unparsed: bool = False, limit: int = 20) -> str:
    """列出本地 PDF 与解析状态（裁剪后的精简视图）。

    limit 硬钳在 50：上下文预算正是这条工具存在的理由，不能靠调用方自觉。
    """
    raw = _call("GET", "/api/papers/local")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # 上游返回非 JSON 时原样透出，不吞

    if not isinstance(payload, dict) or not payload.get("ok"):
        return raw  # 业务错误（4xx/5xx）原样返回，保留 status/detail

    data = payload.get("data") or {}

    # T2-5: Flask 侧「documents 目录不存在」返回 200 + error（前端在用，状态码不能改成 4xx），
    # 于是 _call 会把它包成 ok=true。这里必须如实上抛，否则模型会答「本地没有 PDF」。
    dir_error = data.get("error")
    if dir_error:
        return json.dumps(
            {
                "ok": False,
                "error": dir_error,
                "hint": "检查 DOCUMENTS_DIR 是否存在",
            },
            ensure_ascii=False,
            indent=2,
        )

    all_papers = data.get("papers") or []
    parsed_count = sum(1 for paper in all_papers if paper.get("parsed"))
    unparsed_count = len(all_papers) - parsed_count

    selected = [
        paper for paper in all_papers
        if not (only_unparsed and paper.get("parsed"))
    ]

    # T2-4: 上限硬钳 50。只有下限的话，limit=10000 就把「避免灌满上下文」直接绕过。
    cap = max(1, min(int(limit), 50))
    shown = selected[:cap]
    items = [
        {
            "filename": paper.get("filename"),
            "parsed": bool(paper.get("parsed")),
            "paper_id": paper.get("paper_id"),
            "title": paper.get("title"),
            "file_size_mb": paper.get("file_size_mb"),
            "paragraph_count": paper.get("paragraph_count"),
        }
        for paper in shown
    ]

    return json.dumps(
        {
            "ok": True,
            "total": len(all_papers),
            "parsed_count": parsed_count,
            "unparsed_count": unparsed_count,
            "returned": len(items),
            "truncated": len(selected) > len(items),
            "note": f"已截断，共 {len(selected)} 篇" if len(selected) > len(items) else "",
            "papers": items,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(
    description=(
        "提交本地 PDF 解析入库任务（POST /api/papers/parse_async）。"
        "① **只能解析 documents/ 目录里已存在的 PDF，本工具不能上传文件**；"
        "② 立即返回 task_id，用 mcp__scipal-generate__review_task_status 轮询（间隔 ≥5 s）；"
        "③ 大文件可能几分钟（实测约 3.8 s/MB，16 MB 以上会超过 MCP 的 60 s，故必须异步）；"
        "④ 解析入库**不写 Chroma 索引**，所以不保证立刻能被混合检索命中，"
        "但可以按 paper_id 查详情。"
    )
)
def parse_paper(filename: str) -> str:
    """提交解析任务，立即返回 {"task_id": ...}（异步，不等待解析完成）。"""
    return _call("POST", "/api/papers/parse_async", {"filename": filename})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
