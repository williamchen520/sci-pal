"""最小 MCP Server —— 阶段零 A 临时验证脚本（非业务代码）。

用途
    验证「Python 侧 stdio MCP Server → DSH Desktop」通路是否成立。
    只暴露一个工具：ping → {"ok": true}

依赖
    SciPal venv 中已存在官方 mcp Python SDK（实测 v2.2.0）。
    注意：mcp 2.x 已把 FastMCP 更名为 MCPServer（mcp.server.mcpserver.MCPServer），
    本脚本按 2.x API 编写，不能在 mcp 1.x 下运行。

运行
    # 1) 作为 stdio server（由 DSH 的 dsh-mcp-client 启动，不手工运行）
    venv_sciPal_py312\\Scripts\\python.exe tests\\mcp_ping_server.py

    # 2) 自测：以独立 stdio 子进程方式连自己，验证 initialize / tools/list / tools/call
    venv_sciPal_py312\\Scripts\\python.exe tests\\mcp_ping_server.py --selftest

约束
    stdio 模式下 stdout 是 JSON-RPC 通道，本脚本在 server 模式下绝不向 stdout 打印任何内容。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TypedDict

from mcp.server.mcpserver import MCPServer

SERVER_NAME = "scipalhello"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions="SciPal 阶段零 A 连通性验证服务器，仅提供 ping 工具。",
)


class PingResult(TypedDict):
    """ping 的结构化返回：固定 {"ok": true}。"""

    ok: bool


@mcp.tool(
    description='连通性探针：无参数，返回 {"ok": true}',
    structured_output=True,
)
def ping() -> PingResult:
    """返回固定 JSON，用于确认 MCP 通路端到端可用。"""
    return {"ok": True}


async def _selftest() -> int:
    """以 client 身份启动本文件的 stdio server 子进程并调用 ping。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_path = Path(__file__).resolve()
    params = StdioServerParameters(command=sys.executable, args=[str(server_path)])

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("ping", {})

    # mcp 2.x：CallToolResult 使用 snake_case 属性（is_error / structured_content）
    is_error = getattr(result, "is_error", None)
    structured = getattr(result, "structured_content", None)
    text_blocks = [
        block.text for block in (result.content or [])
        if getattr(block, "type", "") == "text"
    ]
    if structured is not None:
        payload = structured
    elif text_blocks:
        payload = json.loads(text_blocks[0])
    else:
        payload = None

    print(f"[selftest] serverName   : {SERVER_NAME} {SERVER_VERSION}")
    print(f"[selftest] tools        : {[t.name for t in tools.tools]}")
    print(f"[selftest] is_error     : {is_error}")
    print(f"[selftest] payload      : {payload!r}")

    ok = (
        is_error is False
        and payload == {"ok": True}
        and [t.name for t in tools.tools] == ["ping"]
    )
    print(f"[selftest] RESULT       : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(asyncio.run(_selftest()))
    # 标准 stdio 常驻模式：由 DSH 的 dsh-mcp-client 拉起
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
