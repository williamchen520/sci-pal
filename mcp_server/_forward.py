"""公共薄转发层（阶段五-B）。

从 `mcp_server/scipal_server.py` **原样抽出**的 HTTP 传输层，供 `search_server.py`
与 `generate_server.py` 复用。逻辑与旧文件逐字一致，未做任何行为改动。

三条铁律（违反即设计失效）
    1. 只依赖标准库 + `mcp` SDK；**绝不 import 任何 SciPal 内部模块**
       （禁止 `from services...`、禁止 `import api_server`、禁止把项目根注入 sys.path）。
       一旦 import，embedding / reranker 会被加载进该子进程，薄转发设计作废。
    2. 不改 Flask 业务代码，只调现有路由。
    3. stdio 模式下 stdout 是 JSON-RPC 通道，本模块**不向 stdout 打印**。

环境变量
    SCIPAL_BASE_URL   默认 http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_BASE_URL = "http://127.0.0.1:5000"

# 单次 HTTP 读超时。MCP 侧 toolCallTimeoutMs 上限 60 秒，此处留 15 秒余量。
HTTP_TIMEOUT_SECONDS = 45.0


def base_url() -> str:
    """当前 SciPal API 基址（不含尾部斜杠）。"""
    return (
        os.environ.get("SCIPAL_API_BASE")
        or os.environ.get("SCIPAL_BASE_URL", DEFAULT_BASE_URL)
    ).rstrip("/")


def _not_running_error(detail: str) -> ToolError:
    """服务不通时的错误文案：给出可操作指引，而不是「请手动起 Flask」。

    注意：绝不在工具调用内同步等待服务启动——冷启动 30–45 秒会顶到 MCP 的
    60 秒上限。启动交给 scripts/sciPal_watchdog.py（工具调用之外）。
    """
    return ToolError(
        f"SciPal API 未启动（{base_url()}）。\n"
        f"推荐：安装一次性自启（计划任务），之后无需人工介入：\n"
        f"    powershell -File scripts/install_autostart.ps1\n"
        f"若已安装自启：服务可能正在预热，等 30–45 秒后重试。\n"
        f"临时应急（服务会随终端退出被回收，非持久）：\n"
        f"    python scripts/sciPal_watchdog.py --once\n"
        f"（详情：{detail}）"
    )


def _http_raw(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, str]:
    """发一次 HTTP 请求，返回 (status, body_text)。

    基础设施故障（连接失败 / 超时）一律转成受控 ToolError，不抛裸异常。
    """
    url = f"{base_url()}{path}"
    headers = {"Accept": "application/json"}
    token = os.environ.get("SCIPAL_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
