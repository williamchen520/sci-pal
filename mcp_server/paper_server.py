"""scipal-paper MCP server — thin read-only forwarding to SciPal API.

serverName: scipal-paper
transport: stdio

Hard rules:
  · no SciPal internal imports, no model loading
  · only existing HTTP routes
  · stdout is JSON-RPC; never print to stdout
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from _forward import _call, _path_segment  # noqa: E402


def _load_env_file() -> None:
    for name in ("SCIPAL_API_ENV_FILE", "SCIPAL_CODE_ENV_FILE"):
        path = os.environ.get(name, "")
        if not path or not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

SERVER_NAME = "scipal-paper"
SERVER_VERSION = "0.1.0"

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SciPal 单篇论文分析工具（薄转发本地 Flask API）。"
        "所有工具只读；outline → paragraph → sentence → evidence，"
        "code links / module map / data flow 来自已绑定 code library。"
        "不自动下载、不执行代码、不伪造模块说明。"
    ),
)


def _paper(paper_id: str) -> str:
    return _path_segment(paper_id)


@mcp.tool(description="单篇论文健康检查（GET /api/health）。")
def paper_health() -> str:
    return _call("GET", "/api/health")


@mcp.tool(description="论文章节目录（GET /api/papers/<id>/outline）。")
def paper_outline(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/outline")


@mcp.tool(
    description=(
        "按 section 取第一段（GET /api/papers/<id>/paragraphs/first）。"
        "section 为空表示解析顺序第一段；figure/table caption 默认排除。"
    )
)
def paper_first_paragraph(paper_id: str, section: str = "", include_captions: bool = False) -> str:
    query = urlencode(
        {"section": section, "include_captions": "1" if include_captions else "0"}
    )
    return _call("GET", f"/api/papers/{_paper(paper_id)}/paragraphs/first?{query}")


@mcp.tool(description="单篇论文聚合分析（GET /api/papers/<id>/analysis）。q 为空则不查 evidence。")
def paper_analysis(
    paper_id: str,
    q: str = "",
    top_k: int = 8,
    compact: bool = True,
    include_sections: bool = False,
) -> str:
    query = urlencode(
        {
            "q": q,
            "top_k": top_k,
            "compact": "1" if compact else "0",
            "include_sections": "1" if include_sections else "0",
        }
    )
    return _call("GET", f"/api/papers/{_paper(paper_id)}/analysis?{query}")


@mcp.tool(
    description=(
        "句级证据（POST /api/papers/<id>/evidence）："
        "paragraph vector recall + sentence FTS，返回 sentence_id/para_id/section。"
    )
)
def paper_evidence(paper_id: str, query: str, top_k: int = 8) -> str:
    return _call(
        "POST",
        f"/api/papers/{_paper(paper_id)}/evidence",
        {"query": query, "top_k": top_k},
    )


@mcp.tool(description="论文代码链接（GET /api/papers/<id>/code-links）。")
def paper_code_links(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/code-links")


@mcp.tool(description="论文已绑定 code library（GET /api/papers/<id>/code-libraries）。")
def paper_code_libraries(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/code-libraries")


@mcp.tool(
    description=(
        "按 section_type 取整节（GET /api/papers/<id>/sections/<type>）："
        "results / methods / discussion / abstract 等。"
    )
)
def paper_section(
    paper_id: str,
    section_type: str,
    include_paragraphs: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> str:
    query = urlencode(
        {
            "include_paragraphs": "1" if include_paragraphs else "0",
            "limit": limit,
            "offset": offset,
        }
    )
    return _call(
        "GET",
        f"/api/papers/{_paper(paper_id)}/sections/{_path_segment(section_type)}?{query}",
    )


@mcp.tool(description="论文来源（GET /api/papers/<id>/sources）：jats/html/pdf。")
def paper_sources(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/sources")


@mcp.tool(description="论文 JATS 原生字段（GET /api/papers/<id>/jats）：article-type/sec-type。")
def paper_jats(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/jats")


@mcp.tool(description="论文联邦视图（GET /api/papers/<id>/federated）：按来源分组，不合并分数。")
def paper_federated(paper_id: str, source_kind: str = "") -> str:
    query = urlencode({"source_kind": source_kind}) if source_kind else ""
    suffix = f"?{query}" if query else ""
    return _call("GET", f"/api/papers/{_paper(paper_id)}/federated{suffix}")


@mcp.tool(description="论文 PDF 原生字段（GET /api/papers/<id>/pdf）：page/bbox。")
def paper_pdf(paper_id: str, include_paragraphs: bool = False) -> str:
    query = urlencode({"include_paragraphs": "1" if include_paragraphs else "0"})
    return _call("GET", f"/api/papers/{_paper(paper_id)}/pdf-native?{query}")


@mcp.tool(description="论文 HTML 原生字段（GET /api/papers/<id>/html）：sections/paragraphs。")
def paper_html(paper_id: str, include_paragraphs: bool = False) -> str:
    query = urlencode({"include_paragraphs": "1" if include_paragraphs else "0"})
    return _call("GET", f"/api/papers/{_paper(paper_id)}/html?{query}")


@mcp.tool(description="论文模块表（GET /api/papers/<id>/modules）：文件/单元/imports。")
def paper_modules(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/modules")


@mcp.tool(description="论文数据流（GET /api/papers/<id>/data-flow）：reads/writes artifact。")
def paper_data_flow(paper_id: str) -> str:
    return _call("GET", f"/api/papers/{_paper(paper_id)}/data-flow")


@mcp.tool(
    description=(
        "生成复刻计划（POST /api/papers/<id>/replication-plan）："
        "target 为文件名；只生成计划，不执行。"
    )
)
def paper_replication_plan(paper_id: str, target: str) -> str:
    return _call(
        "POST",
        f"/api/papers/{_paper(paper_id)}/replication-plan",
        {"target": target},
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
