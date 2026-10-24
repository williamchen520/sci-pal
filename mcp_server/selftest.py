"""SciPal MCP 自检 —— 阶段五-C C-1（3 个 server / 22 条断言，逐工具真调用）。

做什么
    对 3 个 server 逐个以 client 身份拉起**独立 stdio 子进程**，跑完整链路：
    initialize → tools/list → 对每个工具做一次真实 HTTP 调用（经 MCP 转发到 Flask）。

断言
    1. tools/list 必须与期望清单**完全一致**（多一个少一个都 FAIL）。
    2. 每个工具至少一次真实调用：`is_error` 必须为 False。
       - 2xx → PASS（显示 status + ok）
       - 4xx → PASS（业务性结果，如不存在的 id → 404，说明参数名与路径正确）
       - 5xx / 连接失败 → FAIL（`is_error=True`，打印错误文本）
    3. **Flask 未启动时直接判 FAIL 并退出**，绝不报 PASS。

运行
    venv_sciPal_py312\\Scripts\\python.exe mcp_server\\selftest.py

退出码
    0 = 全部 PASS，1 = 有 FAIL
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "http://127.0.0.1:5000"

# 测试用「不存在的 id」：命中 404 即证明路由与参数名正确，且不产生副作用
MISSING = "__selftest_missing__"

SERVERS = [
    {
        "label": "scipal (legacy, 回退入口)",
        "file": "scipal_server.py",
        "expected": ["health", "search_papers", "get_paper", "get_abstract", "task_status"],
        "calls": {
            "health": {},
            "search_papers": {"query": "CRISPR", "top_k": 3},
            "get_paper": {"paper_id": MISSING},
            "get_abstract": {"paper_id": MISSING},
            "task_status": {"task_id": MISSING},
        },
    },
    {
        "label": "scipal-search",
        "file": "search_server.py",
        "expected": [
            "health",
            "search_hybrid",
            "search_online",
            "get_paper",
            "download_online_papers",
            "download_status",
        ],
        "calls": {
            "health": {},
            "search_hybrid": {"query": "CRISPR", "top_k": 3},
            # 只取 1 条，减小联网耗时
            "search_online": {"query": "CRISPR", "max_results": 1},
            "get_paper": {"paper_id": MISSING},
            # 空列表 → 400「缺少 pmc_ids」，验证参数名且**不产生下载任务**
            "download_online_papers": {"pmc_ids": []},
            "download_status": {"task_id": MISSING},
        },
    },
    {
        "label": "scipal-generate",
        "file": "generate_server.py",
        # 顺序有讲究：generate_outline 会真提交一次大纲任务，之后 Flask 单线程会被饿住，
        # 所以把它放在**最后**，前面全是轻量只读调用。
        "expected": [
            "health",
            "list_saved_outlines",
            "get_saved_outline",
            "get_review",
            "paper_citation_graph",
            "review_task_status",
            "cancel_review_task",
            "generate_outline",
        ],
        "calls": {
            "health": {},
            "list_saved_outlines": {},
            "get_saved_outline": {"name": MISSING},
            "get_review": {"review_id": MISSING},
            "paper_citation_graph": {"paper_id": MISSING, "max_hops": 1},
            "review_task_status": {"task_id": MISSING},
            # 不存在的 task_id → 404（业务结果算通过），且不产生真实副作用
            "cancel_review_task": {"task_id": MISSING},
            # 真实提交大纲任务（max_papers=2 控制规模）；异步判据在 _run_server 里：
            # 必须 <10s 返回且返回体含 task_id
            "generate_outline": {"topic": "CRISPR delivery", "max_papers": 2},
        },
    },
]


def _base_url() -> str:
    return os.environ.get("SCIPAL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _flask_running() -> bool:
    """用极短超时探测 Flask（不依赖 MCP）。"""
    try:
        with urllib.request.urlopen(f"{_base_url()}/api/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _extract_text(result) -> str:
    """mcp 2.x：CallToolResult.content 是 block 列表，文本在 block.text。"""
    blocks = [
        block.text for block in (result.content or [])
        if getattr(block, "type", "") == "text"
    ]
    return "\n".join(blocks)


def _parse_payload(text: str) -> tuple[object, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "?", "?"
    if not isinstance(payload, dict):
        return "?", "?"
    return payload.get("status"), payload.get("ok")


def _extract_task_id(text: str):
    """取 task_id，兼容 {"ok":...,"data":{"task_id":...}} 与直接 {"task_id":...} 两种形态。"""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and data.get("task_id"):
        return data["task_id"]
    return payload.get("task_id")


async def _run_server(server: dict) -> tuple[int, int]:
    """跑一个 server 的完整链路，返回 (pass, fail)。"""
    path = HERE / server["file"]
    params = StdioServerParameters(command=sys.executable, args=[str(path)])
    passed = 0
    failed = 0

    print(f"\n[server] {server['label']}  ({server['file']})")

    if not path.exists():
        print(f"  [FAIL] 文件不存在：{path}")
        return 0, 1

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            # 保持定义顺序（generate_outline 放最后，避免它起的大纲任务把后续调用饿住）
            expected = server["expected"]

            if names == sorted(expected):
                print(f"  [PASS] tools/list  {len(names)} 个，与期望一致")
                passed += 1
            else:
                print("  [FAIL] tools/list 与期望不一致")
                print(f"         期望: {expected}")
                print(f"         实际: {names}")
                failed += 1

            for name in expected:
                args = server["calls"].get(name, {})
                started = time.time()
                try:
                    result = await session.call_tool(name, args)
                except Exception as exc:  # 调用本身炸了也要计入 FAIL，不吞
                    print(f"  [FAIL] {name:<24} 调用异常: {exc}")
                    failed += 1
                    continue
                elapsed = time.time() - started

                text = _extract_text(result)
                is_error = getattr(result, "is_error", None)

                if is_error:
                    print(f"  [FAIL] {name:<24} is_error=True: {text.strip()[:200]}")
                    failed += 1
                    continue

                # ── 特殊断言（阶段五-C C-1）────────────────────────────────
                if name == "generate_outline":
                    # 异步判据：必须快速返回（<10s）且返回体含 task_id
                    task_id = _extract_task_id(text)
                    good = bool(task_id) and elapsed < 10.0
                    print(
                        f"  [{'PASS' if good else 'FAIL'}] {name:<24} "
                        f"耗时={elapsed:.2f}s task_id={task_id}（要求 <10s 且非空）"
                    )
                    passed += 1 if good else 0
                    failed += 0 if good else 1
                    continue

                if name == "cancel_review_task":
                    # 不存在的 task_id → 404 是业务结果，算通过
                    status, ok = _parse_payload(text)
                    good = status == 404
                    print(
                        f"  [{'PASS' if good else 'FAIL'}] {name:<24} "
                        f"status={status}（期望 404，业务错误算通过）"
                    )
                    passed += 1 if good else 0
                    failed += 0 if good else 1
                    continue

                status, ok = _parse_payload(text)
                print(f"  [PASS] {name:<24} status={status} ok={ok} ({elapsed:.2f}s)")
                passed += 1

    return passed, failed


def main() -> None:
    print("=" * 74)
    print("SciPal MCP selftest —— 3 个 server，逐工具真实调用")
    print(f"Flask 基址: {_base_url()}")
    print("=" * 74)

    if not _flask_running():
        print("\n[FATAL] Flask 未启动 —— 无法做真实 HTTP 调用，本次自检判 FAIL。")
        print("        先启动：python api_server.py（或 scripts/sciPal_watchdog.py --once）")
        print("\nRESULT: FAIL")
        raise SystemExit(1)

    total_pass = 0
    total_fail = 0
    for server in SERVERS:
        passed, failed = asyncio.run(_run_server(server))
        total_pass += passed
        total_fail += failed

    print("\n" + "=" * 74)
    print("汇总")
    print("=" * 74)
    print(f"  server 数      : {len(SERVERS)}")
    print(f"  断言总数       : {total_pass + total_fail}")
    print(f"  PASS           : {total_pass}")
    print(f"  FAIL           : {total_fail}")
    print(f"  RESULT         : {'PASS' if total_fail == 0 else 'FAIL'}")
    raise SystemExit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
