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

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from code_rag.context import build_context as rag_context  # noqa: E402
from code_rag.search import search as rag_search  # noqa: E402
from code_rag.service import health as rag_health  # noqa: E402
from code_rag.trace import trace as rag_trace  # noqa: E402


def _load_env_file() -> None:
    for name in ("SCIPAL_CODE_ENV_FILE", "SCIPAL_API_ENV_FILE"):
        path = os.environ.get(name, "")
        if not path or not Path(path).exists():
            continue
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
        "code_trace 只做 1–3 跳图扩展；code_status 返回索引状态。"
        "rag_plan 只提案，必须由人类审批；rag_dispatch 只派发已批准计划。不要自动改代码。"
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
        "构建 C3 证据包：目标 unit + 目标文件 import + 直接出向依赖。"
        "direction=out（默认）/in/both；不生成最终答案。"
    )
)
def code_context(unit_id: str, library_id: str, max_neighbors: int = 10, direction: str = "out") -> str:
    try:
        result = rag_context(
            unit_id=unit_id,
            library_id=library_id,
            max_neighbors=max(1, min(int(max_neighbors), 30)),
            direction=direction,
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


def _api(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    base = os.environ.get("SCIPAL_API_URL", "http://127.0.0.1:5001").rstrip("/")
    token = os.environ.get("SCIPAL_INTERNAL_TOKEN", "").strip()
    if not token:
        raise ToolError("SCIPAL_INTERNAL_TOKEN is not configured")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-SCIPAL-Internal-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ToolError(f"SciPal API rejected request: {detail}") from None
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"SciPal API unavailable: {exc}") from None


@mcp.tool(
    description=(
        "提交只读 RAG 计划（不执行）。steps_json 是 JSON 数组；每步含 action/rag_id/library_id/query/params。"
        "返回 plan_id 和 plan_hash；必须让人类在 Web 审批后才能 dispatch。不要自动批准。"
    )
)
def rag_plan(intent: str, steps_json: str) -> str:
    try:
        steps = json.loads(steps_json)
        if not isinstance(steps, list):
            raise ValueError("steps_json must be an array")
        result = _api("/api/rag/plans", "POST", {"intent": intent, "steps": steps})
        return json.dumps(result, ensure_ascii=False)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"rag_plan failed: {exc}") from None


@mcp.tool(description="查询 plan 状态与步骤；只读。")
def rag_plan_status(plan_id: str) -> str:
    try:
        return json.dumps(_api(f"/api/rag/plans/{plan_id}"), ensure_ascii=False)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"rag_plan_status failed: {exc}") from None


@mcp.tool(
    description=(
        "派发已经由人类批准的 plan。只接受 approved 状态；不能批准 plan。"
    )
)
def rag_dispatch(plan_id: str) -> str:
    try:
        return json.dumps(
            _api(f"/api/rag/plans/{plan_id}/dispatch", "POST", {}), ensure_ascii=False
        )
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"rag_dispatch failed: {exc}") from None


@mcp.tool(description="查询 RAG job 状态；只读。")
def rag_job_status(job_id: str) -> str:
    try:
        return json.dumps(_api(f"/api/rag/jobs/{job_id}"), ensure_ascii=False)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"rag_job_status failed: {exc}") from None


@mcp.tool(
    description=(
        "通过 RAG Gateway 做只读查询；支持 code_search / evidence_search / doc_search / multi_search。"
        "multi_search 用 rag_ids 逗号分隔（code,literature,docs），分组返回，不跨库合并分数。"
        "code_search 需要 library_id；其他不需要。返回 run_id 和带 evidence_id 的结果。"
    )
)
def rag_query(capability: str, query: str, library_id: str = "", top_k: int = 10, rag_ids: str = "") -> str:
    try:
        return json.dumps(
            _api(
                "/api/rag/query",
                "POST",
                {
                    "capability": capability,
                    "library_id": library_id,
                    "query": query,
                    "top_k": top_k,
                    "rag_ids": [item.strip() for item in rag_ids.split(",") if item.strip()],
                },
            ),
            ensure_ascii=False,
        )
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"rag_query failed: {exc}") from None



def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
