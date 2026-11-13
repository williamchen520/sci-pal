# 实验记录：RAG 控制面 R3 Local Worker

> 日期：2026-11-13  
> 状态：**worker 代码/单元测试完成；未做 app 端到端执行**  
> 代码：`scripts/rag_worker.py`

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

失败：

```text
POST /api/rag/jobs/<id>/fail
```

## 3. 安全

```text
repo path 必须在 allowlist
不支持任意 shell
不支持任意 URL
token 只走 header
```

## 4. 验证

```text
tests.test_rag_worker 2 passed
```

## 5. 未完成

```text
没有启动 app 做真实 lease->ingest->complete
没有 evidence/artifact
没有 rag_query worker
没有 remote/HPC
```

## 6. 下一步

```text
R4 evidence + artifact ledger
或先做 worker 端到端 app 联调
```
