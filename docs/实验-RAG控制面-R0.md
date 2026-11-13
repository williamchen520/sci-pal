# 实验记录：RAG 控制面 R0 Provider Registry

> 日期：2026-11-13  
> 状态：**R0 完成；无任务队列/审批/路由**  
> 代码：`services/rag_control/`

---

## 1. 目标

```text
把现有三个 RAG 注册进控制面
提供只读查询和健康检查
不改变任何检索行为
```

## 2. 注册结果

```text
literature  scipal_rebuild
docs        scipal_docs
code        scipal_code
```

表：

```text
scipal_core.rag_providers
```

字段：

```text
rag_id
version
capabilities
endpoint
database_name
schema_version
model_bindings
resource_profile
data_residency
status
manifest_hash
manifest
```

## 3. Manifest

```text
services/rag_control/manifests/
  literature.json
  docs.json
  code.json
```

种子：

```bash
python scripts/seed_rag_providers.py
```

输出：

```text
RAG_PROVIDERS_SEEDED count=3
```

## 4. API

```text
GET /api/rag/providers
GET /api/rag/providers/<rag_id>
GET /api/rag/providers/<rag_id>/health
```

只读；不触发入库，不路由查询。

## 5. 健康检查

### code

```text
type: http
url_env: SCIPAL_CODE_API_URL
path: /health
```

实际：

```text
active
latency 344 ms
```

### literature

```text
type: postgres
dsn_env: SCIPAL_PG_CORPUS_DSN
query: to_regclass('public.papers')
```

实际：

```text
active
```

### docs

```text
type: postgres
dsn_env: SCIPAL_DOCS_DSN
query: to_regclass('docs_rag.documents')
```

实际：

```text
unknown
detail: missing SCIPAL_DOCS_DSN
```

没有伪造 healthy。

## 6. 验证

```text
tests.test_rag_control 5 passed
validate_arch 214/214 OK
```

API 实际：

```text
GET /api/rag/providers
-> code, docs, literature

GET /api/rag/providers/code/health
-> status=active
```

## 7. 当前缺口

```text
docs DSN 未配置
没有 rag_jobs
没有 plan/approval
没有路由
没有证据账本
```

## 8. 下一步 R1

```text
rag_plans
rag_plan_steps
rag_jobs
rag_runs
lease + heartbeat
```

R0 只是“知道有哪些 RAG”，还不能调度。
