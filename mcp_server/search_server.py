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
import urllib.parse
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


@mcp.tool(
    description=(
        "异步提交「下载 + 入库 + 向量化」任务（POST /api/ingest），"
        "**立即返回 task_id，不要同步等待**；用 check_ingest_status 轮询（间隔 ≥5 s）。"
        "每 batch_size 篇提交一次数据库事务（默认 5），中途失败只回滚当批，"
        "已完成的批次保留；任务状态存 ingest_tasks 表，Flask 重启后仍可查。"
        "pmc_ids 传 PMCID 列表，例如 [\"PMC13613157\", \"PMC13615804\"]。"
    )
)
def download_and_index(pmc_ids: list[str], batch_size: int = 5) -> str:
    """提交下载并向量化任务，立即返回 {"task_id": ...}。"""
    return _call(
        "POST",
        "/api/ingest",
        {"pmc_ids": pmc_ids, "batch_size": batch_size},
    )


@mcp.tool(
    description=(
        "查询下载/入库任务状态（GET /api/ingest/<task_id>）。"
        "status 取值：queued / running / partial / completed / failed / cancelled；"
        "返回 processed（已处理）、imported（已入库）、failed（失败数）、error（失败明细）。"
    )
)
def check_ingest_status(task_id: str) -> str:
    """按 task_id 查询下载并向量化任务的进度。"""
    return _call("GET", f"/api/ingest/{_path_segment(task_id)}")


@mcp.tool(
    description=(
        "结构化证据包（POST /api/evidence/search）：返回段落级上下文、章节路径、"
        "命中句 page/bbox 与引用/图表链接；不返回裸句子。"
    )
)
def search_evidence(query: str, top_k: int = 8, paper_id: str = "") -> str:
    """检索并返回 DSH 可直接使用的证据包。"""
    return _call(
        "POST",
        "/api/evidence/search",
        {"query": query, "top_k": top_k, "paper_id": paper_id},
    )


@mcp.tool(
    description=(
        "二次下钻（GET /api/evidence/context）：根据 sentence_id 或 para_id "
        "取命中句、前后文、章节路径；Agent 觉得上下文不足时调用。"
    )
)
def get_context(
    sentence_id: str = "",
    para_id: str = "",
    paper_id: str = "",
    before: int = 1,
    after: int = 1,
    query: str = "",
) -> str:
    """返回句子/段落及其父级上下文。"""
    params = urllib.parse.urlencode(
        {
            "sentence_id": sentence_id,
            "para_id": para_id,
            "paper_id": paper_id,
            "before": before,
            "after": after,
            "query": query,
        }
    )
    return _call("GET", f"/api/evidence/context?{params}")


@mcp.tool(
    description=(
        "强制校验（POST /api/verify）：生成后回传 answer 与 evidence_ids，"
        "返回 ok/missing_ids/uncited_claims/quote_mismatch；ok=false 时不得作为正式结论。"
    )
)
def verify_answer(answer: str, evidence_ids: list[str]) -> str:
    """确定性校验答案引用与冲突结构。"""
    return _call("POST", "/api/verify", {"answer": answer, "evidence_ids": evidence_ids})


@mcp.tool(description="列出文献监测 profile（GET /api/watch/profiles）。")
def watch_profiles() -> str:
    """返回所有 profile 的配置与上次/下次运行时间。"""
    return _call("GET", "/api/watch/profiles")


@mcp.tool(
    description=(
        "触发一次文献监测（POST /api/watch/profiles/<id>/run）："
        "按窗口检索、去重、排序、摘要级入库并返回简报。"
    )
)
def watch_run(profile_id: int) -> str:
    """运行一个 profile，返回简报与统计。"""
    return _call("POST", f"/api/watch/profiles/{profile_id}/run")


@mcp.tool(
    description="最近一期监测简报（GET /api/watch/profiles/<id>/latest），不触发新运行。"
)
def watch_latest(profile_id: int) -> str:
    """返回最近一次运行与入选条目。"""
    return _call("GET", f"/api/watch/profiles/{profile_id}/latest")


@mcp.tool(description="创建系统综述项目（POST /api/review-projects）。")
def review_project_create(name: str, field_text: str = "", pico: dict | None = None) -> str:
    return _call(
        "POST",
        "/api/review-projects",
        {"name": name, "field_text": field_text, "pico": pico or {}},
    )


@mcp.tool(description="纳入/排除筛选（POST /api/review-projects/<id>/screen）。")
def review_screen(project_id: str, paper_id: str, decision: str, reason: str = "") -> str:
    return _call(
        "POST",
        f"/api/review-projects/{_path_segment(project_id)}/screen",
        {"paper_id": paper_id, "decision": decision, "reason": reason},
    )


@mcp.tool(description="PRISMA 计数（GET /api/review-projects/<id>/prisma）。")
def review_prisma(project_id: str) -> str:
    return _call("GET", f"/api/review-projects/{_path_segment(project_id)}/prisma")


@mcp.tool(description="提取证据表（POST /api/review-projects/<id>/evidence）。")
def review_evidence(project_id: str) -> str:
    return _call("POST", f"/api/review-projects/{_path_segment(project_id)}/evidence")


@mcp.tool(description="证据表 CSV（GET /api/review-projects/<id>/evidence.csv）。")
def review_evidence_csv(project_id: str) -> str:
    return _call("GET", f"/api/review-projects/{_path_segment(project_id)}/evidence.csv")


@mcp.tool(description="自动抽取 PICO（POST /api/review-projects/<id>/pico）。")
def review_extract_pico(project_id: str) -> str:
    return _call("POST", f"/api/review-projects/{_path_segment(project_id)}/pico")


@mcp.tool(description="双人筛选一致性 Cohen's kappa（GET /api/review-projects/<id>/kappa）。")
def review_kappa(project_id: str) -> str:
    return _call("GET", f"/api/review-projects/{_path_segment(project_id)}/kappa")


@mcp.tool(description="风险偏倚评估（GET/POST /api/review-projects/<id>/risk-of-bias）。")
def review_risk_of_bias(project_id: str, assess: bool = True) -> str:
    return _call(
        "POST" if assess else "GET",
        f"/api/review-projects/{_path_segment(project_id)}/risk-of-bias",
        {} if assess else None,
    )


@mcp.tool(description="把一次 Watch 运行结果导入综述项目（POST /api/review-projects/<id>/from-watch）。")
def review_import_watch(project_id: str, run_id: int) -> str:
    return _call(
        "POST",
        f"/api/review-projects/{_path_segment(project_id)}/from-watch",
        {"run_id": int(run_id)},
    )


@mcp.tool(description="综述项目一页纸简报（GET /api/review-projects/<id>/brief，Markdown）。")
def review_brief(project_id: str) -> str:
    return _call("GET", f"/api/review-projects/{_path_segment(project_id)}/brief")


@mcp.tool(description="综述项目 HTML 报告（GET /api/review-projects/<id>/report.html）。")
def review_report_html(project_id: str) -> str:
    return _call("GET", f"/api/review-projects/{_path_segment(project_id)}/report.html")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
