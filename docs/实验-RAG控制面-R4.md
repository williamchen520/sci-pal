# 实验记录：RAG 控制面 R4 Evidence / Artifact Ledger

> 日期：2026-11-13  
> 状态：**账本表/API 可用；真实检索证据待 R5**  
> 代码：`services/rag_control/ledger.py`

---

## 1. 目标

```text
每条证据可反查
每次运行有 artifact
append-only
```

## 2. 表

```text
rag_evidence
  evidence_id
  run_id
  plan_id / step_id
  rag_id / library_id / snapshot
  source_path
  start_line / end_line
  content_hash
  model_version
  score
  metadata

rag_artifacts
  artifact_id
  run_id
  kind
  uri
  sha256
  size_bytes
  license
  metadata
```

## 3. API

```text
GET  /api/rag/runs/<run_id>/evidence
POST /api/rag/runs/<run_id>/evidence      worker token
GET  /api/rag/runs/<run_id>/artifacts
POST /api/rag/runs/<run_id>/artifacts     worker token
```

## 4. Ledger smoke

真实 run：

```text
run_eac9f07dd55c
```

append：

```text
evidence ev_c3d5edc10663
artifact art_6e168cd6aba9
```

list：

```text
evidence 1
artifact 1
```

随后删除测试 plan/run；临时数据已清理。

## 5. Worker manifest

worker 完成后写：

```text
G:/runs/rag_artifacts/run_<run_id>.json
```

内容：

```text
run_id
job_id
plan_id
rag_id
library_id
snapshot
repo_path
repo_url
ref
exit_code
seconds
```

并以 `kind=run_manifest` 注册 artifact。

## 6. 验证

```text
tests.test_rag_ledger 3 passed
tests.test_rag_worker 2 passed
validate_arch 232/232 OK
```

## 7. 边界

```text
evidence smoke 是合成字段
不是真实 code_search 返回
worker manifest 未做一次完整 E2E
```

不把 smoke 当真实证据。

## 8. 下一步 R5

```text
Gateway query
真实检索 evidence
DSH rag_plan 工具
```
