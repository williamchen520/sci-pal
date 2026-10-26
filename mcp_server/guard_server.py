"""SciPal MCP Server · guard —— 领域词表校验（scipal-guard）。

serverName: `scipal-guard`   transport: stdio

定位：术语校验与证据落地检查。
    · 实体（Gene/Chemical/Variant/Disease）→ PubTator3 + HGNC 词表
    · 正文是否出现过 → paragraphs_fts
    · 方法/技术/主题短语 → 不判

设计铁律与 search/generate server 一致：薄转发，只调 Flask 现有路由，
不 import 任何 SciPal 内部模块、不加载模型、不打 stdout。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from _forward import _call, _path_segment  # noqa: E402

SERVER_NAME = "scipal-guard"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SciPal 术语校验工具（薄转发本地 Flask /api/guard/*）。"
        "guard_check 对一段文本做实体词表校验，返回 unknown/variant/ambiguous 计数与明细；"
        "guard_term 查某个词的标准 ID、别名与分层；guard_stats 返回词表规模。"
        "只判实体类术语，方法与技术类不判。"
    ),
)


@mcp.tool(
    description=(
        "术语校验（POST /api/guard/check）：对文本做实体词表校验。"
        "返回 checked / unknown / unknown_ratio / counts / issues。"
        "只判实体（Gene/Chemical/Variant/Disease），方法/技术/主题短语不判。"
    )
)
def guard_check(text: str) -> str:
    """校验一段文本的领域实体术语。"""
    return _call("POST", "/api/guard/check", {"text": text})


@mcp.tool(
    description=(
        "查词（GET /api/guard/term/<term>）：返回标准 ID、canonical、aliases、"
        "出现论文数与词表分层（curated/broad/weak）。"
    )
)
def guard_term(term: str) -> str:
    """查询单个术语的词表条目。"""
    return _call("GET", f"/api/guard/term/{_path_segment(term)}")


@mcp.tool(description="词表统计（GET /api/guard/stats）：条目数、可匹配 surface 数、按类型/分层分布。")
def guard_stats() -> str:
    """返回 guard 词表规模统计。"""
    return _call("GET", "/api/guard/stats")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
