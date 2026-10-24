"""SciPal MCP Server —— 单进程薄转发（阶段三 · 首个增量）。

设计裁决（见 docs/DSH契约要点.md §8.2）
    只起一个 MCP server 进程，**不承载任何业务逻辑**，把工具调用转发到 SciPal 已有的
    Flask API。原因是 embedding / reranker / ChromaDB 都是进程级资源，本机 8GB 显存
    装不下第二份模型；Flask 进程本就常驻并已加载模型，转发是零增量成本。

两条硬性约束（违反即设计失效）
    1. 纯 HTTP 客户端：本文件**不 import 任何 SciPal 内部模块**（禁止 `from services...`、
       禁止 `import app`、禁止 sys.path 注入）。一旦 import，模型会被加载进该子进程，
       单进程设计立刻作废。本文件的全部依赖只有标准库 + `mcp` SDK。
    2. 不改 Flask 业务代码：只调现有路由。路由不够用时应报告，而不是在这里加路由。

环境变量
    SCIPAL_BASE_URL   默认 http://127.0.0.1:5000

运行
    # 由 DSH 的 dsh-mcp-client 以 stdio 拉起（不手工运行）：
    venv_sciPal_py312\\Scripts\\python.exe mcp_server\\scipal_server.py

    # 自检（独立子进程跑完整协议链路）：
    venv_sciPal_py312\\Scripts\\python.exe mcp_server\\selftest.py

约束
    stdio 模式下 stdout 是 JSON-RPC 通道，本文件在 server 模式下绝不向 stdout 打印内容。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

SERVER_NAME = "scipal"
SERVER_VERSION = "0.1.0"
DEFAULT_BASE_URL = "http://127.0.0.1:5000"

# 单次 HTTP 读超时。MCP 侧 toolCallTimeoutMs 上限 60 秒，此处留 15 秒余量。
HTTP_TIMEOUT_SECONDS = 45.0

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SciPal 学术文献工具集（薄转发 Flask API）。"
        "所有工具只读；长任务请使用返回的 job 句柄配合 task_status 轮询。"
    ),
)


# ---------------------------------------------------------------------------
# HTTP 传输层（仅标准库）
# ---------------------------------------------------------------------------


def base_url() -> str:
    """当前 SciPal API 基址（不含尾部斜杠）。"""
    return os.environ.get("SCIPAL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _not_running_error(detail: str) -> ToolError:
    return ToolError(
        f"SciPal API 未启动：连接 {base_url()} 失败，请先运行 python api_server.py"
        f"（详情：{detail}）"
    )


def _http_raw(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, str]:
    """发一次 HTTP 请求，返回 (status, body_text)。

    基础设施故障（连接失败 / 超时）一律转成受控 ToolError，不抛裸异常。
    """
    url = f"{base_url()}{path}"
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # 4xx/5xx：HTTP 层可达，交由调用方按状态码分流
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise _not_running_error(str(exc.reason)) from None
    except (TimeoutError, OSError) as exc:
        raise ToolError(
            f"SciPal API 请求超时或网络错误（>{HTTP_TIMEOUT_SECONDS:.0f}s）：{url}（{exc}）"
        ) from None


def _call(method: str, path: str, payload: dict[str, Any] | None = None) -> str:
    """转发一次调用，统一包装成 JSON 文本。

    - 2xx      → {"ok": true,  "status": ..., "data": ...}
    - 4xx      → {"ok": false, "status": ..., "detail": ...}（业务性结果，如 404）
    - 5xx      → ToolError（服务端故障，is_error=True）
    - 连不上   → ToolError（明确提示 Flask 未启动）
    """
    status, body = _http_raw(method, path, payload)
    try:
        parsed: Any = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = body

    if status >= 500:
        raise ToolError(f"SciPal API 返回 {status}：{str(parsed)[:500]}")

    if status >= 400:
        return json.dumps(
            {"ok": False, "status": status, "detail": parsed},
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps(
        {"ok": True, "status": status, "data": parsed},
        ensure_ascii=False,
        indent=2,
    )


def _path_segment(value: str) -> str:
    """把用户输入安全地拼进 URL 路径段（paper_id / task_id 可能含空格等字符）。"""
    return urllib.parse.quote(str(value), safe="")


# ---------------------------------------------------------------------------
# 工具面（首个增量：5 个只读工具）
# 参数名以 api_server.py 路由实际读取的为准：
#   /api/search/hybrid 读的是 `q`（不是 query），此处对外暴露 query，转发时映射为 q。
#   /api/abstracts/<id> 按 **pmid** 查询（路由内 SQL 是 WHERE pmid = ?）。
# ---------------------------------------------------------------------------


@mcp.tool(description="SciPal 服务健康检查（GET /api/health）。无参数。")
def health() -> str:
    """检查 SciPal Flask API 是否在线，返回 status / service / version / db_exists。"""
    return _call("GET", "/api/health")


@mcp.tool(
    description=(
        "混合检索论文（POST /api/search/hybrid）：本地库 + 可选在线 NCBI PubMed/PMC。"
        "use_online 默认 false（服务端默认 true 会联网，容易超过 MCP 60 秒上限）；"
        "需要在线检索时显式传 true。"
    )
)
def search_papers(query: str, top_k: int = 10, use_online: bool = False) -> str:
    """按关键词检索论文。返回合并后的论文列表与计数。"""
    return _call(
        "POST",
        "/api/search/hybrid",
        {"q": query, "top_k": top_k, "use_online": use_online},
    )


@mcp.tool(description="获取单篇论文的详细信息（GET /api/papers/<paper_id>）：元数据 + 引用/被引/相似论文。")
def get_paper(paper_id: str) -> str:
    """按 paper_id 查询论文详情。"""
    return _call("GET", f"/api/papers/{_path_segment(paper_id)}")


@mcp.tool(
    description=(
        "获取摘要库中的摘要（GET /api/abstracts/<paper_id>）。"
        "注意：该路由按 **PMID** 查询，paper_id 参数请传 PMID。"
    )
)
def get_abstract(paper_id: str) -> str:
    """按 PMID 查询摘要内容。"""
    return _call("GET", f"/api/abstracts/{_path_segment(paper_id)}")


@mcp.tool(
    description=(
        "查询长任务状态（GET /api/tasks/<task_id>）。"
        "长任务工具会立即返回 job 句柄，用本工具轮询进度/结果。"
    )
)
def task_status(task_id: str) -> str:
    """按 task_id 查询统一任务表状态。"""
    return _call("GET", f"/api/tasks/{_path_segment(task_id)}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
