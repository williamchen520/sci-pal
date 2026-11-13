# SciPal RAG 控制面设计 v1

> 日期：2026-11-13  
> 状态：设计，不写实现  
> 目标：单机可跑，未来可扩到服务器 / HPC  
> 原则：控制面统一，数据面隔离；不预造 K8s

---

## 1. 结论

```text
不做 RAG OS
做 RAG Control Plane
```

```text
控制面：注册、路由、任务、模型、配额、审计
数据面：每个 RAG 独立 DB / 独立服务 / 独立索引
```

当前：

```text
literature RAG   scipal_rebuild
docs RAG         scipal_docs
code RAG         scipal_code
```

未来：

```text
更多 RAG
专用 embedding / rerank / generation 模型
本地 GPU / 远端 API / HPC
```

---

## 2. 分层

```text
DSH / Web UI
    │
    ▼
SciPal RAG Gateway
    │
    ├── Registry        有哪些 RAG
    ├── Router          该用哪个
    ├── Scheduler       什么时候跑、跑在哪
    ├── Model Registry  用哪个模型
    └── Audit/Lineage   谁在什么时候用了什么
    │
    ▼
RAG workers
    ├── literature
    ├── docs
    └── code
         │
         ▼
   独立数据库 / 索引
```

---

## 3. 控制面与数据面边界

### 控制面负责

```text
RAG provider 注册
capability 声明
任务排队/租约/重试
资源请求与放置
模型绑定
配额/权限
健康检查
审计与血缘
```

### 控制面不负责

```text
不存向量
不存论文/代码正文
不 import RAG 内部模块
不直接写 RAG 数据库
不替 RAG 做检索
```

### RAG 负责

```text
自己的 parser / index / search
自己的 schema/migration
自己的模型调用
自己的结果格式
```

---

## 4. 数据库放哪

### v1：放 `scipal_core`

```text
scipal_core
  libraries             已有
  rag_providers
  rag_jobs
  rag_runs
  rag_models
  rag_events
```

理由：

```text
控制面是平台元数据
任务量单机可控
少一个数据库
```

### 何时拆 `scipal_control`

```text
任务量 > 10 万
多团队共用
控制面独立部署
```

拆分时只换 DSN，不换表结构。

---

## 5. 核心表

### 5.1 rag_providers

```text
rag_id
version
display_name
capabilities jsonb        code_search / evidence_search / doc_search
endpoint                  http://... 或 worker://...
database_name             仅元数据，不存 DSN
schema_version
model_bindings jsonb
resource_profile jsonb
data_residency
status                     active/degraded/offline
manifest_hash
created_at / updated_at
```

### 5.2 rag_jobs

```text
job_id
rag_id
library_id
job_type                  ingest / reindex / eval
priority
status                    queued/leased/running/succeeded/failed/canceled
resource_request jsonb
payload jsonb             snapshot/source/commit
lease_owner
lease_expires_at
attempts
max_attempts
created_at / started_at / finished_at
error
```

索引：

```text
(status, priority, created_at)
(rag_id, library_id)
(lease_expires_at)
```

### 5.3 rag_runs

```text
run_id
job_id
rag_id
library_id
snapshot
model_version
started_at / finished_at
exit_code
artifact_uri
metrics jsonb
```

### 5.4 rag_models

```text
model_id
provider                  local / deepseek / remote / hpc
kind                      embedding / rerank / generation
dimension
context_window
endpoint
license
cost_profile
status
```

### 5.5 rag_events

```text
event_id
rag_id
job_id / run_id
event_type
detail jsonb
created_at
```

用于血缘/审计，不用来存正文。

---

## 6. Provider Manifest

每个 RAG 注册时提交：

```yaml
rag_id: code
version: 0.2.0
capabilities:
  - code_search
  - code_context
  - code_trace
endpoint: http://127.0.0.1:5010
database: scipal_code
schema_version: 1
models:
  embedding: bge-small-zh-v1.5
  rerank: none
resources:
  cpu: 2
  ram_gb: 4
  gpu: optional
data_residency: local
```

规则：

```text
manifest 是控制面唯一依赖
控制面不读 RAG 代码
endpoint 可以是本机、远端、worker
```

---

## 7. 任务模型

### 7.1 入库

```text
长任务
幂等：library_id + snapshot + model_version
可重试
可取消
```

状态机：

```text
queued -> leased -> running -> succeeded
                    └-> failed -> retry / dead
```

### 7.2 查询

```text
短任务
有 deadline
有 budget
有 fallback
不排队等 HPC
```

查询不写 `rag_jobs`，除非需要审计。

---

## 8. 调度：单机版

```text
PostgreSQL
  SELECT ... FOR UPDATE SKIP LOCKED
  lease_owner + lease_expires_at
```

Worker：

```text
scripts/rag_worker.py
  register
  poll jobs
  heartbeat
  execute
  write run/event
```

优点：

```text
不引入 Redis
不引入 K8s
崩溃后 lease 过期可回收
```

---

## 9. 扩展：远端 / HPC

### 远端 worker

```text
worker 主动连控制面（outbound）
不需要公网入站
```

### HPC / Slurm

```text
worker 在 login node
  -> sbatch
  -> 轮询 sacct
  -> 产物回传
```

只接：

```text
批量入库 / 重建索引 / 评测
```

不接：

```text
在线查询
```

### 放置策略

```text
local GPU      embedding / rerank
remote API     generation
HPC            batch ingest / large index
```

控制面只记录 `resource_profile` 和 `data_residency`，不猜。

---

## 10. 模型与索引绑定

```text
index 必须记录 embedding_model + dimension
查询必须用同一模型
换模型 = reindex
```

禁止：

```text
A 模型建索引，B 模型查询
多个 RAG 共用向量表
```

---

## 11. 路由

```text
query
  -> capability 分类
  -> 选主 RAG
  -> 可选 fanout
  -> 证据归一化
```

证据契约：

```text
rag_id
library_id
snapshot
model_version
source
score
```

规则：

```text
不跨库混排
不把代码证据当文献证据
不把 C3 的 read 结果当 code_search 命中
```

---

## 12. Gateway API

```text
GET  /api/rag/providers
POST /api/rag/query
POST /api/rag/ingest
GET  /api/rag/jobs/<id>
POST /api/rag/jobs/<id>/cancel
```

请求示例：

```json
{
  "capability": "code_search",
  "library_id": "lib_xxx",
  "query": "normalize_total",
  "deadline_ms": 3000
}
```

DSH 仍可走现有 MCP；Gateway 是平台层统一入口，不替代 MCP。

---

## 13. 权限与数据

```text
library_id 作用域
workspace ACL
provider token
data_residency
cloud_gate
```

远端模型：

```text
只发聚合/脱敏产物
原始数据不出本地
```

---

## 14. 单机落地顺序

### R0：注册表

```text
rag_providers 表
manifest
health
不改变现有调用
```

### R1：任务表 + 本地 worker

```text
rag_jobs / rag_runs
code-rag ingest 先接
lease + heartbeat
```

### R2：模型注册

```text
rag_models
embedding 绑定
```

### R3：远端 worker

```text
outbound polling
```

### R4：HPC

```text
Slurm adapter
```

### R5：多 RAG 路由

```text
capability 路由
证据归一化
```

---

## 15. 计划表

| 阶段 | 工作 | 人日 |
|---|---|---:|
| R0 | provider registry + manifest + health | 2 |
| R1 | jobs/runs + lease + local worker | 4 |
| R2 | model registry + index binding | 2 |
| R3 | remote worker + token | 3 |
| R4 | Slurm adapter | 3 |
| R5 | gateway 路由 + 证据契约 | 3 |
| 合计 |  | **17 人日** |

单机先做 R0/R1，之后按需。

---

## 16. Gate

```text
G0 控制面不 import RAG 内部模块
G1 同一 snapshot 重跑不产生重复数据
G2 lease 过期可回收
G3 远端 worker 无公网入站
G4 换 embedding 必须 reindex
G5 多 RAG 结果不跨库混排
```

任何一条失败：

```text
不上多 RAG 路由
```

---

## 17. 不要做

```text
不要上 K8s（现在）
不要自写工作流引擎
不要共享向量库
不要让 RAG 互相调用
不要用 LangChain 当控制面
不要为了“平台感”做通用 DSL
```

---

## 18. 一句话

```text
控制面只调度任务、模型、资源
数据面永远独立
单机用 Postgres 队列
远端/HPC 用同一 worker 协议
```
