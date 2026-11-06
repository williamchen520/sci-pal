# SciPal MCP 化与 DSH 大脑：细化策略

> 日期：2026-11-07  
> 前置：总方案  
> 状态：执行设计，不涉及代码实现

---

## 1. 范围与假设

```text
单开发者
单机 Windows + Docker/WSL
SciPal 已有 Flask、PG、pgvector、MCP 薄转发
DSH 已有 MCP client、subagent、workflow
```

策略：

```text
不重写 SciPal
不建微服务
先只读，再实验，再 intake
每个阶段有验收门槛
```

---

## 2. 契约 v1

### 2.1 MCP server 划分

| Server | 工具 | 模式 |
|---|---|---|
| `scipal-search` | search_papers, get_paper, get_evidence, trace_sentence | 同步只读 |
| `scipal-qa` | ask_question, verify_answer | 异步 |
| `scipal-review` | generate_outline, generate_review | 异步 |
| `scipal-guard` | guard_check, guard_term | 同步 |
| `scipal-experiment` | submit_experiment, get_experiment, list_plugins | 异步 |
| `scipal-jobs` | get_task, cancel_task, list_tasks | 同步 |

不新增：

```text
数据库直连工具
任意 SQL 工具
任意 shell 工具
```

### 2.2 工具返回

```text
data
citations
provenance
task_id（异步）
next_cursor（分页）
```

### 2.3 错误模型

```text
code
message
retryable
details
```

统一错误码：

```text
INVALID_INPUT
NOT_FOUND
CONFLICT
RATE_LIMITED
TIMEOUT
UPSTREAM_ERROR
PERMISSION_DENIED
```

### 2.4 资源 URI

```text
scipal://paper/<paper_id>
scipal://evidence/<evidence_id>
scipal://experiment/<run_id>
scipal://plugin/<name>
scipal://artifact/<sha256>
```

大对象不塞 tool 返回。

---

## 3. SciPal 改造

### 3.1 目录

```text
services/mcp_gateway/
  server.py
  auth.py
  errors.py
  schemas.py
  adapters/
    search.py
    evidence.py
    qa.py
    review.py
    guard.py
    experiment.py
```

### 3.2 原则

```text
adapter 只调用现有 service
不复制业务逻辑
不改现有 Flask 路由
MCP 可单独启停
```

### 3.3 鉴权

```text
本地 token
workspace_id
tool allowlist
```

不把 token 放进 URL。

---

## 4. 插件内核

### 4.1 目录

```text
plugins/algorithms/
  <name>/
    manifest.json
    plugin.py
    requirements.txt
    README.md
    tests/
```

### 4.2 manifest

```json
{
  "name": "hyde",
  "version": "0.1.0",
  "slot": "query_planner",
  "entrypoint": "plugin:HyDE",
  "paper_doi": "",
  "repo_url": "",
  "commit": "",
  "license": "MIT",
  "permissions": ["no_network"],
  "params_schema": {}
}
```

### 4.3 槽位接口

```python
class QueryPlanner(Protocol):
    def plan(self, query: str, ctx: QueryContext) -> list[str]: ...

class Verifier(Protocol):
    def verify(self, answer: Answer, evidence: EvidenceSet) -> list[Finding]: ...

class Agent(Protocol):
    def answer(self, question: str, tools: ToolContext) -> AgentAnswer: ...
```

### 4.4 生命周期

```text
registered
validated
staging
enabled
disabled
archived
```

生产启用必须人工。

### 4.5 权限

```text
no_network
no_db_write
no_secrets
max_tokens
max_latency_ms
```

---

## 5. 实验服务

### 5.1 表

```sql
experiment_runs (
  run_id, name, corpus_hash, gold_hash, seed,
  baseline, status, created_at, finished_at
)

experiment_variants (
  variant_id, run_id, plugin, config jsonb, status
)

experiment_metrics (
  id, variant_id, metric, value,
  ci_low, ci_high
)

experiment_artifacts (
  id, run_id, kind, uri, sha256
)
```

### 5.2 固定条件

```text
corpus snapshot
gold set
embedding model
generator model
top_k
rerank
temperature
seed
```

### 5.3 对照

```text
baseline
plugin
plugin + rerank（可选）
```

### 5.4 统计

```text
paired bootstrap 10k
95% CI
非劣性门槛
```

---

## 6. DSH 适配

### 6.1 Skill Pack

```text
skills/scipal-research/
skills/scipal-algorithm-intake/
skills/scipal-plugin-eval/
```

### 6.2 命令

```text
/scipal search <query>
/scipal evidence <query>
/scipal intake <paper-url-or-doi>
/scipal eval <plugin> --gold <set>
```

### 6.3 intake workflow

```text
Phase 1 论文
Phase 2 代码
Phase 3 设计摘要
Phase 4 插件草案
Phase 5 测试
Phase 6 评测
Phase 7 报告
```

每阶段写入 artifact：

```text
paper.json
repo.json
design.md
plugin.diff
test.log
metrics.json
report.md
```

### 6.4 审批点

```text
许可证确认
依赖安装
外部代码执行
插件进 staging
插件进 production
```

---

## 7. 第一批插件

| 插件 | 槽位 | 依赖 | 工作量 | 优先级 |
|---|---|---|---|---|
| HyDE | query_planner | LLM | S | P0 |
| Multi-Query | query_planner | 无 | S | P0 |
| MMR / reorder | context_builder | 无 | S | P0 |
| Adaptive-RAG | query_planner | 分类器 | M | P1 |
| NLI 引用校验 | verifier | NLI 模型 | M | P0 |
| Claim decomposition | verifier | LLM | M | P1 |
| Self-RAG | agent/verifier | LLM | L | P2 |
| CRAG | agent/verifier | LLM | L | P2 |
| PaperQA2 | agent | 外部包 | L | P3 |
| RAPTOR | index | 重建索引 | L | P3 |
| GraphRAG | index | 图构建 | L | P4 |

P0 先做：

```text
HyDE
Multi-Query
MMR
NLI
```

---

## 8. PaperQA2 接入

```text
slot: agent
tools: search_papers / get_paper / get_evidence
mode: staging only
network: 默认关闭，使用本地 corpus
```

必须记录：

```text
paperqa version
model
embedding
top_k
seed
```

对比：

```text
SciPal baseline QA
PaperQA2 agent
```

指标：

```text
answer correctness
citation precision/recall
unsupported claim rate
latency
cost
```

---

## 9. 评测数据

优先级：

```text
1. SciFact（已有）
2. 内部 20 题回归
3. 1 万篇全文 gold（后续）
4. PaperBench / LAB-Bench（远期）
```

反幻觉指标：

```text
unsupported claim rate
citation precision
citation recall
refusal accuracy
```

---

## 10. 安全

| 风险 | 控制 |
|---|---|
| prompt injection | 论文内容只作数据 |
| 恶意代码 | 无网络沙箱 |
| 依赖投毒 | lockfile + 白名单 |
| 许可证 | 不明确不合并 |
| 密钥泄露 | 沙箱无 secrets |
| 数据污染 | staging + 人工审批 |
| 评测泄漏 | 固定 holdout |

---

## 11. 里程碑

### M0 契约（2–3 天）

```text
schema
error model
manifest
experiment tables
```

### M1 只读 MCP（3–5 天）

```text
search
paper
evidence
guard
DSH 可调用
```

### M2 实验服务（5–7 天）

```text
plugin registry
sandbox
baseline
metrics
report
```

### M3 第一批插件（5–7 天）

```text
HyDE
Multi-Query
MMR
NLI
```

### M4 intake（5–10 天）

```text
paper -> repo -> design -> plugin draft
人工审批
```

### M5 半自动（持续）

```text
DSH 生成 + 评测
人只审批
```

---

## 12. 验收

```text
M1：DSH 能完成 10 个检索/证据任务
M2：同一插件可重复跑出相同指标
M3：至少 1 个插件显著优于 baseline 或非劣
M4：一篇论文可生成可运行插件草案
M5：外部代码不进入生产主机
```

---

## 13. 风险

```text
DSH 上下文预算
MCP 长任务超时
插件非确定性
外部仓库不可复现
评测集太小
单开发者维护成本
```

缓解：

```text
小步交付
先只读
固定评测
staging
人工审批
```

---

## 14. 结论

```text
先做 M0 + M1
再做 M2 + P0 插件
最后做 PaperQA2 / intake
```

最小闭环：

```text
scipal-experiment MCP
+ plugin manifest
+ 固定评测
+ DSH skill
```


---

## 13. 核心原则（新增）

```text
SciPal 主架构不变
baseline 永远可运行
插件即插即用
用完可去
```

### 13.1 主线不变

```text
核心检索/问答/入库/表结构不改
插件不能要求核心迁移
插件不能 monkeypatch 核心
```

### 13.2 插件隔离

```text
独立目录
独立 manifest
独立依赖
独立配置
独立表（plugin_<name>_*）
```

### 13.3 可移除

```text
禁用插件 -> baseline 立即恢复
卸载插件 -> 删除目录 + 自己的表
核心代码和数据不受影响
```

### 13.4 失败回退

```text
插件异常 -> 记录 -> 回退 baseline
插件超时 -> 回退 baseline
插件未启用 -> baseline
```

### 13.5 实验要求

```text
每次实验必须有 baseline
baseline 与 plugin 同 corpus / 同 gold / 同参数
插件不能改变评测口径
```

### 13.6 禁止

```text
插件改核心表
插件改核心路由
插件全局注入
插件常驻后台写库
插件依赖未固定
```
