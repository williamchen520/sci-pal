"""SciPal MCP Server 自检 —— 阶段三交付物。

做什么
    以 client 身份拉起 `scipal_server.py` 的**独立 stdio 子进程**，跑完整链路：
    initialize → tools/list → tools/call(health)，并针对 Flask 的两种状态分别断言。

断言
    a) tools/list 恰好返回 5 个工具：health / search_papers / get_paper / get_abstract / task_status
    b) Flask 正在运行（能连上 /api/health）→ tools/call(health) 必须 is_error=False 且包装了真实响应
    c) Flask 未运行 → tools/call(health) 必须 is_error=True 且文本含「SciPal API 未启动」

运行
    venv_sciPal_py312\\Scripts\\python.exe mcp_server\\selftest.py

退出码
    0 = PASS，1 = FAIL
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parent / "scipal_server.py"
DEFAULT_BASE_URL = "http://127.0.0.1:5000"
EXPECTED_TOOLS = ["health", "search_papers", "get_paper", "get_abstract", "task_status"]


def _base_url() -> str:
    return os.environ.get("SCIPAL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _flask_running() -> bool:
    """用极短超时探测 Flask 是否在线（不依赖 MCP）。"""
    try:
        with urllib.request.urlopen(f"{_base_url()}/api/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _extract_text(result) -> str:
    """mcp 2.x：CallToolResult.content 是 content block 列表，文本在 block.text。"""
    blocks = [
        block.text for block in (result.content or [])
        if getattr(block, "type", "") == "text"
    ]
    return "\n".join(blocks)


async def _run() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)

            tools_ok = names == sorted(EXPECTED_TOOLS)

            flask_running = _flask_running()
            result = await session.call_tool("health", {})
            is_error = getattr(result, "is_error", None)
            text = _extract_text(result)

            if flask_running:
                # 真实响应：形如 {"ok": true, "status": 200, "data": {"status": "ok", ...}}
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
                health_ok = (
                    is_error is False
                    and isinstance(payload, dict)
                    and payload.get("ok") is True
                    and str((payload.get("data") or {}).get("status", "")).lower() == "ok"
                )
                expected = "Flask 在跑 → 返回真实响应（is_error=False）"
            else:
                health_ok = is_error is True and "SciPal API 未启动" in text
                expected = "Flask 未跑 → 返回明确错误文本（is_error=True）"

    server_info = getattr(init, "serverInfo", None)
    print(f"[selftest] serverInfo   : {server_info}")
    print(f"[selftest] tools.count  : {len(names)}")
    print(f"[selftest] tools        : {names}")
    print(f"[selftest] expected     : {sorted(EXPECTED_TOOLS)}")
    print(f"[selftest] flask        : {'RUNNING' if flask_running else 'NOT RUNNING'} ({_base_url()})")
    print(f"[selftest] expected     : {expected}")
    print(f"[selftest] health.error : {is_error}")
    print("[selftest] health.text  : " + text.strip().replace("\n", " | ")[:400])

    ok = tools_ok and health_ok
    print(f"[selftest] RESULT       : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
