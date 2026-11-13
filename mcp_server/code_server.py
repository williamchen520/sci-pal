"""SciPal code MCP server — read-only scipal-code tools.

stdio only. Never imports Flask or the literature API.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from code_rag.context import build_context as rag_context  # noqa: E402
from code_rag.search import search as rag_search  # noqa: E402
from code_rag.service import health as rag_health  # noqa: E402
from code_rag.trace import trace as rag_trace  # noqa: E402


def _load_env_file() -> None:
    path = os.environ.get("SCIPAL_CODE_ENV_FILE", "")
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

SERVER_NAME = "scipal-code"
mcp = MCPServer(
    SERVER_NAME,
    version="0.1.0",
    instructions=(
        "只读代码库工具，按 library_id 隔离。"
        "code_search 返回符号/路径/行号/片段；code_context 返回 unit + import + 邻居；"
        "code_trace 只做 1–3 跳图扩展；code_status 返回索引状态。不要自动改代码。"
    ),
)


@mcp.tool(
    description=(
        "按 library_id 检索代码单元：exact symbol + trigram + vector + RRF。"
        "library_id 必填；返回 unit_id/symbol/path/start_line/end_line/snippet/score。"
    )
)
def code_search(query: str, library_id: str, top_k: int = 10, snapshot_id: str = "") -> str:
    try:
        hits = rag_search(
            query,
            library_id=library_id,
            top_k=max(1, min(int(top_k), 50)),
            snapshot_id=snapshot_id,
        )
        return json.dumps({"query": query, "library_id": library_id, "hits": hits}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"code_search failed: {exc}") from None


@mcp.tool(
    description=(
        "代码索引状态：schema version、库数、snapshot 数、unit 数。"
        "library_id 可选；不传则返回全局状态。"
    )
)
def code_status(library_id: str = "") -> str:
    try:
        result = rag_health()
        if library_id:
            import psycopg

            dsn = os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
            with psycopg.connect(dsn) as conn:
                result["library"] = {
                    "library_id": library_id,
                    "snapshots": conn.execute(
                        "SELECT count(*) FROM code_rag.code_snapshots WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                    "units": conn.execute(
                        "SELECT count(*) FROM code_rag.code_units WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                }
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"code_status failed: {exc}") from None


@mcp.tool(
    description=(
        "构建 C3 证据包：目标 unit + 目标文件 import + 直接邻居。"
        "用于符号定位后再 read 确认；不生成最终答案。"
    )
)
def code_context(unit_id: str, library_id: str, max_neighbors: int = 10) -> str:
    try:
        result = rag_context(
            unit_id=unit_id,
            library_id=library_id,
            max_neighbors=max(1, min(int(max_neighbors), 30)),
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"code_context failed: {exc}") from None

@mcp.tool(
    description=(
        "沿 code_edges 做有界图扩展：direction=out|in|both，max_hops<=3。"
        "返回节点、边、路径证据；不生成最终答案。"
    )
)
def code_trace(
    unit_id: str,
    library_id: str,
    direction: str = "both",
    max_hops: int = 2,
    max_nodes: int = 30,
) -> str:
    try:
        result = rag_trace(
            unit_id=unit_id,
            library_id=library_id,
            direction=direction,
            max_hops=max_hops,
            max_nodes=max_nodes,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"code_trace failed: {exc}") from None


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
