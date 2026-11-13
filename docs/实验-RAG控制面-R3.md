# 实验记录：RAG 控制面 R3 Local Worker + E2E

> 日期：2026-11-13  
> 状态：**E2E 通过；临时数据已清理**  
> 代码：`scripts/rag_worker.py`、`code_rag/ingest.py`

---

## 1. 目标

```text
lease job
执行 code_ingest
注册 index binding
complete / fail
```

## 2. Worker

```text
SCIPAL_API_BASE
SCIPAL_RAG_WORKER_TOKEN
SCIPAL_RAG_REPO_ROOT
SCIPAL_CODE_DSN
SCIPAL_RAG_EMBED_MODEL
SCIPAL_RAG_EMBED_DIM
```

流程：

```text
POST /api/rag/jobs/lease
  -> validate repo_path under REPO_ROOT
  -> python -m code_rag.ingest
  -> heartbeat
  -> POST /api/rag/index-bindings
  -> POST /api/rag/jobs/<id>/complete
```

## 3. E2E 结果

临时 repo：

```text
G:/repos/rag-e2e-demo
f8bd141
demo.py
```

临时 library：

```text
lib_38261ec44aee
```

Plan：

```text
plan_1bdb58aaf073
```

状态：

```text
plan      succeeded
job       succeeded
run       1, exit_code 0
binding   BAAI/bge-small-zh-v1.5 / 512
          snapshot snap_fbfcd666c9c5744b
units     3
```

## 4. 发现并修复的问题

### 4.1 worker 丢失 library_id

`library_id` 在 job 顶层，worker 只从 step params 取，导致 binding 400。

修复：

```text
params.setdefault("library_id", job["library_id"])
```

### 4.2 跨库 unit_id 碰撞

`code_units.unit_id` 只按文件/符号生成，不带 library/snapshot。

结果：

```text
第一个库（空 library_id）写入 3 units
第二个库同路径 -> 主键冲突 -> DO NOTHING
-> 第二个库 0 units，但 ingest 仍 exit 0
```

修复：

```text
unit_id = stable("unit", library_id, snapshot_id, parsed_unit_id)
parent / edges 同步映射
```

回归：

```text
tests.test_code_rag_unit_scope 3 passed
```

## 5. 验证

```text
tests.test_code_rag_unit_scope 3
tests.test_code_rag_parsers
tests.test_rag_worker 2
tests.test_rag_plans 5
tests.test_rag_models 4
tests.test_rag_control 5
合计 20 passed
```

## 6. 清理

```text
临时 plan/job/run 已删除
临时 library 已删除
临时 index binding 已删除
临时 code units 已删除
临时 repo 已删除
```

## 7. 边界

```text
只验证 code_ingest
没有 rag_query worker
没有 evidence/artifact
```

## 8. 下一步 R4

```text
evidence ledger
artifact ledger
run manifest
```
