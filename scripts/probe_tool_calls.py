"""Probe local small-model tool-call stability (no SciPal import).

Sends a set of tool-call prompts to Ollama and validates the JSON shape.
Usage: python scripts/probe_tool_calls.py --model qwen2.5:3b --runs 10
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from typing import Any, Dict, List

PROMPTS = [
    ("profile", "分析 D:/data/cohort.xlsx 的字段分布", {"path", "project_id"}),
    ("aggregate", "按 sex 分组统计 D:/data/cohort.csv", {"path", "project_id", "group_by"}),
    ("sample", "给 D:/data/cohort.tsv 生成脱敏样例", {"path", "project_id"}),
    ("profile", "看看 D:/data/lab.xlsx 有哪些列", {"path", "project_id"}),
    ("aggregate", "按 stage 和 sex 聚合 D:/data/trial.csv", {"path", "project_id", "group_by"}),
    ("sample", "从 D:/data/patients.xlsx 抽样 5 行", {"path", "project_id"}),
    ("profile", "读取 D:/data/raw.tsv 的列类型", {"path", "project_id"}),
    ("aggregate", "统计 D:/data/cohort.xlsx 每个 age 的人数", {"path", "project_id", "group_by"}),
    ("sample", "D:/data/notes.docx 做个脱敏摘要", {"path", "project_id"}),
    ("profile", "D:/data/cohort.csv 缺失值多吗", {"path", "project_id"}),
]

SCHEMA = (
    "You are a tool planner. Return ONLY JSON with shape "
    '{"tool":"data_profile|data_aggregate|data_sample","args":{"path":string,'
    '"project_id":string,"group_by":array optional}}. '
    "project_id must be 'probe'. No markdown, no explanation."
)

MULTI = (
    "Plan two tool calls for: 分析 D:/data/cohort.csv，先 profile 再按 sex aggregate。"
    ' Return ONLY JSON: {"steps":[{"tool":"data_profile","args":{...}},'
    '{"tool":"data_aggregate","args":{...}}]}.'
)


def chat(model: str, prompt: str, host: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SCHEMA if prompt != MULTI else "Return only JSON."},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    return data.get("message", {}).get("content", "")


def validate(text: str, required: set[str]) -> bool:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    if "steps" in data:
        steps = data.get("steps") or []
        return len(steps) >= 2 and all("tool" in step and "args" in step for step in steps)
    args = data.get("args") or {}
    return data.get("tool") in {"data_profile", "data_aggregate", "data_sample"} and required.issubset(args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    results: List[Dict[str, Any]] = []
    started = time.time()
    for name, prompt, required in PROMPTS[: args.runs]:
        try:
            text = chat(args.model, prompt, args.host)
            ok = validate(text, required)
        except Exception as exc:  # noqa: BLE001
            text, ok = f"ERROR {exc}", False
        results.append({"case": name, "ok": ok, "raw": text[:160]})
        print(("PASS " if ok else "FAIL ") + name, text[:100].replace("\n", " "), flush=True)
    multi = False
    try:
        multi = validate(chat(args.model, MULTI, args.host), set())
    except Exception:  # noqa: BLE001
        pass
    passed = sum(1 for item in results if item["ok"])
    print(
        json.dumps(
            {
                "model": args.model,
                "single_step": f"{passed}/{len(results)}",
                "multi_step": multi,
                "seconds": round(time.time() - started, 1),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
