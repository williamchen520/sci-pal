# SciPal RAG 控制面与科研追溯方案 v1

> 日期：2026-11-13  
> 状态：设计，不是实现  
> 目标：单机可跑，未来扩到服务器 / HPC  
> 核心：控制面统一，数据面隔离，人类授权，证据可追溯

---

## 1. 结论

```text
不做 RAG OS
不做大模型开会
做 RAG Control Plane + 科研追溯
```

```text
DSH / DeepSeek   理解意图、拆解计划、生成回答
人类             审批、授权、撤销
控制面           校验、排队、放置、审计
RAG workers      独立入库 / 检索
证据账本         每条证据可反查
运行清单         代码、环境、结果可复现
```

---

## 2. 现状

当前已有三个 RAG：

```text
literature RAG   scipal_rebuild
docs RAG         scipal_docs
code RAG         scipal_code
```

共同问题：

```text
谁被调用、为什么被调用，没有统一记录
入库任务没有统一队列
模型和索引版本没有统一绑定
证据散落在各 RAG 内部
代码/环境/结果没有统一复现包
```

---

## 3. 总体架构

```text
用户
  │
  ▼
DSH + DeepSeek
  意图理解 / 计划拆解 / 结果汇总
  │
  ├── Plan（只读提案）
  │      │
  │      ▼
  │   人类审批（不可由 DSH 自批）
  │      │
  │      ▼
  └── RAG Gateway / Control Plane
         ├── Provider Registry
         ├── Model Registry
         ├── Plan / Approval
         ├── Job Scheduler
         ├── Placement
         ├── Quota / ACL
         └── Evidence / Artifact Ledger
                │
                ▼
         RAG workers
           literature / docs / code
                │
                ▼
         独立数据库 / 索引
```

---

## 4. 角色边界

### DSH + DeepSeek

```text
理解自然语言
拆解多步任务
选择候选 RAG
生成 Plan
调用 Gateway
汇总证据
解释结果
```

不负责：

```text
任务队列
lease / heartbeat
资源放置
重试
审批
数据库写入
```

### 人类

```text
批准 / 修改 / 拒绝 Plan
批准高风险步骤
设定预算/范围
撤销
审计
```

### 控制面

```text
唯一执行事实源
计划校验
队列/租约
模型/资源放置
配额/审计
```

### RAG worker

```text
自己的 parser / index / search
自己的数据库
自己的模型调用
```

---

## 5. Plan → Approve → Dispatch

```text
1. 用户提出请求
2. DSH/DeepSeek 生成 Plan
3. 人类查看 Plan
4. 批准 / 修改 / 拒绝
5. 控制面校验并派发
6. worker 执行
7. 证据/产物写入账本
8. DSH 汇总回答
```

### Plan 对象

```text
plan_id
intent
steps[]
  step_id
  action          rag_query / rag_ingest / reindex / eval
  rag_id
  library_id
  query / snapshot
  depends_on
  timeout
  budget
risk_level        low / medium / high
status            draft/proposed/approved/dispatched/running/done/failed
plan_hash
created_by
approved_by
approved_at
expires_at
```

任何修改：

```text
新 plan_hash
旧审批失效
重新审批
```

### 审批矩阵

| 操作 | 审批 |
|---|---|
| 只读单 RAG 查询 | 计划级 |
| 多 RAG fanout | 计划级 |
| 新建/重建索引 | 单步 |
| HPC 批量 | 单步 + 预算 |
| 删除库 | 强制人工 |
| 改代码/补丁 | 强制人工 |
| 导出数据 | 单步 + 数据分级 |

禁止：

```text
DSH 调用 approve
DeepSeek 调用 approve
Agent 自批
```

---

## 6. 数据库

### v1：`scipal_core`

```text
libraries              已有
rag_providers
rag_models
rag_plans
rag_plan_steps
rag_jobs
rag_runs
rag_evidence
rag_artifacts
rag_events
```

任务量大后再拆 `scipal_control`，表结构不变。

### rag_providers

```text
rag_id
version
display_name
capabilities jsonb
endpoint
database_name
schema_version
model_bindings jsonb
resource_profile jsonb
data_residency
status
manifest_hash
created_at / updated_at
```

### rag_jobs

```text
job_id
rag_id
library_id
job_type
priority
status
resource_request jsonb
payload jsonb
lease_owner
lease_expires_at
attempts
max_attempts
created_at / started_at / finished_at
error
```

### rag_runs

```text
run_id
job_id
rag_id
library_id
snapshot
model_version
env_hash
exit_code
artifact_uri
metrics jsonb
started_at / finished_at
```

### rag_evidence

```text
evidence_id
plan_id / step_id / run_id
rag_id
library_id
snapshot
source_path
start_line / end_line
content_hash
model_version
score
retrieved_at
```

### rag_artifacts

```text
artifact_id
run_id
kind              code / diff / render / dataset / log
uri
sha256
size
license
created_at
```

---

## 7. Provider Manifest

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
控制面不 import RAG 内部模块
```

---

## 8. 模型与索引

```text
index 与 embedding_model + dimension 绑定
查询必须使用同一模型
换模型 = reindex
```

禁止：

```text
A 模型建索引，B 模型查询
多个 RAG 共用向量表
```

模型注册：

```text
model_id
provider      local / deepseek / remote / hpc
kind          embedding / rerank / generation
dimension
context_window
endpoint
license
cost_profile
status
```

---

## 9. 调度

### 单机

```text
PostgreSQL
  FOR UPDATE SKIP LOCKED
  lease_owner + lease_expires_at
```

Worker：

```text
register
poll
heartbeat
execute
write run/evidence/artifact
```

不引入 Redis / K8s。

### 状态机

```text
queued -> leased -> running -> succeeded
                    └-> failed -> retry / dead
```

### 幂等

```text
idempotency_key =
  hash(rag_id + library_id + snapshot + operation)
```

### 优先级

```text
在线查询 > 交互式入库 > 批量重建
```

---

## 10. 放置

```text
local GPU      embedding / rerank
remote API     generation
HPC / Slurm    batch ingest / large index
```

### 远端 worker

```text
worker 主动连控制面
不需要公网入站
```

### HPC

```text
login node worker
  -> sbatch
  -> sacct 轮询
  -> 产物回传
```

只接批量任务，不接在线查询。

---

## 11. Gateway API

```text
GET  /api/rag/providers
POST /api/rag/plans
POST /api/rag/plans/<id>/approve
POST /api/rag/plans/<id>/dispatch
GET  /api/rag/plans/<id>
POST /api/rag/jobs/<id>/cancel
GET  /api/rag/jobs/<id>
```

查询示例：

```json
{
  "capability": "code_search",
  "library_id": "lib_xxx",
  "query": "normalize_total",
  "deadline_ms": 3000
}
```

---

## 12. DSH 工具

```text
rag_plan
  -> plan_id + 步骤预览

rag_plan_status
  -> proposed/approved/running

rag_dispatch
  -> 只接受 approved plan

rag_job_status
  -> 进度/证据/产物
```

DSH 不持有：

```text
queue 状态
lease
worker token
数据库 DSN
```

---

## 13. 证据可追溯

每条证据必须能回答：

```text
来自哪个 RAG
哪个 library
哪个 snapshot/commit
哪个文件/行
哪个模型
哪次任务
谁批准
```

回答里显示行内引用：

```text
[ev_123]
```

点击打开证据卡：

```text
source_path
commit
start_line-end_line
content_hash
rag_id / model_version
```

---

## 14. 代码与复现包

保存代码不够，要保存“能复现的包”：

```text
code
diff
environment.lock
OCI image + digest
input hash
parameters
random seed
test results
render artifact
run_manifest.json
```

### run_manifest

```text
code_hash
env_hash
input_hash
output_hash
model_version
command
exit_code
```

### 导出

```text
RO-Crate / JSON
  README.md
  plan.json
  evidence.jsonl
  code/
  environment.lock
  inputs/
  outputs/
  tests/
  LICENSE
```

---

## 15. 安全

```text
library ACL
workspace ACL
scoped provider token
data residency
cloud_gate
```

远端模型：

```text
只发聚合/脱敏产物
原始数据不出本地
```

---

## 16. 观测

```text
任务状态
队列长度
worker 心跳
GPU/显存
每 RAG 延迟/错误率
每 query 证据数
每次运行成本
```

血缘：

```text
plan -> job -> run -> evidence -> artifact
```

---

## 17. 单机落地

```text
Docker Compose
  postgres
  app
  code API
  worker
```

先接：

```text
code RAG ingest
```

不改变现有 DSH MCP 调用。

---

## 18. 计划

| 阶段 | 工作 | 人日 |
|---|---|---:|
| R0 | provider registry + manifest + health | 2 |
| R1 | plans + approvals + jobs/runs + lease | 4 |
| R2 | model registry + index binding | 2 |
| R3 | local worker + code ingest | 3 |
| R4 | evidence/artifact ledger | 3 |
| R5 | remote worker + HPC adapter | 4 |
| R6 | Gateway 路由 + DSH 工具 | 3 |
| 合计 |  | **21 人日** |

单机先做 R0–R4。

---

## 19. Gate

```text
G0 控制面不 import RAG 内部模块
G1 同一 snapshot 重跑不重复
G2 lease 过期可回收
G3 每条证据可反查 source/commit
G4 每次运行有 manifest
G5 人类审批不可被 agent 绕过
G6 多 RAG 不跨库混排
```

任何一条失败：

```text
不开放多 RAG 自动路由
```

---

## 20. 不做

```text
不做 RAG OS
不做大模型开会
不上 K8s（现在）
不自写工作流引擎
不共享向量库
不让 RAG 互相调用
不用 LangChain 当控制面
```

---

## 21. 参考项目

这些是模式参考，不是整套照搬。

### 调度与执行

| 项目 | 借什么 |
|---|---|
| [Kueue](https://kueue.sigs.k8s.io/) | 队列、优先级、配额、抢占 |
| [Volcano](https://volcano.sh/) | 批处理调度 |
| [Ray Serve](https://docs.ray.io/en/latest/serve/index.html) | 模型/actor 放置 |
| [Argo Workflows](https://argoproj.github.io/workflows/) | 长任务 DAG、重试 |
| [Temporal](https://temporal.io/) | 持久化工作流、超时 |
| [Slurm](https://slurm.schedmd.com/) | HPC 批处理 |

### 模型服务

| 项目 | 借什么 |
|---|---|
| [KServe](https://kserve.github.io/website/) | 模型声明、健康、版本 |
| [vLLM](https://docs.vllm.ai/) | 本地/远端 LLM 服务 |
| [TEI](https://huggingface.co/docs/text-embeddings-inference) | embedding 服务 |

### 元数据与血缘

| 项目 | 借什么 |
|---|---|
| [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry.html) | 模型版本 |
| [OpenLineage](https://openlineage.io/) | 任务血缘 |
| [PROV-O](https://www.w3.org/TR/prov-o/) | 证据/过程模型 |
| [RO-Crate](https://www.researchobject.org/ro-crate/) | 研究包导出 |
| [SPDX](https://spdx.dev/) | 许可证 |
| [CycloneDX](https://cyclonedx.org/) | SBOM |

### 大公司产品思路

| 产品 | 借什么 |
|---|---|
| [Vertex AI RAG Engine](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview) | corpus/index/model 分层 |
| [Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html) | 知识库与模型解耦 |
| [Azure AI Search](https://learn.microsoft.com/azure/search/) | 检索服务独立 |
| [Databricks Mosaic AI Vector Search](https://docs.databricks.com/aws/en/generative-ai/vector-search) | 索引/模型/评测分层 |

### RAG 产品

| 项目 | 借什么 | 不借什么 |
|---|---|---|
| [RAGFlow](https://github.com/infiniflow/ragflow) | 文档解析/引用 UX | 一体化内核 |
| [Dify](https://github.com/langgenius/dify) | 工作流 UI | 当调度器 |
| [LlamaIndex](https://docs.llamaindex.ai/) | 数据连接器 | 当控制面 |
| [Haystack](https://haystack.deepset.ai/) | pipeline 组合 | 当队列 |

### 协议

| 项目 | 借什么 |
|---|---|
| [MCP](https://modelcontextprotocol.io/) | 工具契约 |
| [OpenTelemetry](https://opentelemetry.io/) | trace/metrics/logs |

---

## 22. 一句话

```text
DSH 提议
人授权
控制面执行
证据账本留痕
运行清单可复现
```

不追求“模型开会”，追求“科研过程可复核”。


## 证据裁决原则

```text
每个 RAG 分组保留原始证据与分数
不跨库归一化、不投票、不合成唯一结论
机器只能给初步信号：supported / conflicting / insufficient
冲突必须并排展示，不能折叠成一个分数
最终裁决由人完成
```

这不是能力缺失，而是科研平台的责任边界：

```text
机器负责检索、分组、初步判断
人负责证据取舍、冲突裁决、结论署名
```
