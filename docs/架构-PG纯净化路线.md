# PostgreSQL 纯净化路线图与 Schema 差异

> 日期：2026-11-02  
> 目标：PostgreSQL 成为唯一业务运行库，SQLite 退役  
> 当前结论：**可以做到，但不是一次性切换。**

## 1. 现状基线

生产 SQLite：

```text
G:\sciPal_deploy\data\research.db
```

生产 PostgreSQL：

```text
scipal_bench
```

Schema 对比结果：

```text
SQLite 应用表       72
PostgreSQL 表       60
共同表              60
SQLite-only         12
PostgreSQL-only     0
```

原始报告：

```text
eval/results/schema_parity_prod.json
```

复现：

```powershell
python scripts/schema_parity.py `
  --sqlite G:\sciPal_deploy\data\research.db `
  --pg-dsn $env:SCIPAL_PG_DSN `
  --out eval/results/schema_parity_prod.json
```

## 2. Schema 差异清单

### 2.1 SQLite-only 表

| 表 | 类别 | 处理 |
|---|---|---|
| `experiments` | 实验 | 补 PG schema + 回填 |
| `experiment_revisions` | 实验 | 补 PG schema + 回填 |
| `experiment_signatures` | 实验 | 补 PG schema + 回填 |
| `experiment_audit` | 实验 | 补 PG schema + 回填 |
| `experiment_access_requests` | 实验 | 补 PG schema + 回填 |
| `projects` | 项目 | 补 PG schema + 回填 |
| `project_members` | 项目 | 补 PG schema + 回填 |
| `dual_write_outbox` | 迁移基础设施 | 最终删除 |
| `papers_fts` | SQLite FTS5 | PG 已有 `papers.search_vector` + GIN |
| `paragraphs_fts` | SQLite FTS5 | PG 已有 `paragraphs.search_vector` + GIN |
| `sentences_fts` | SQLite FTS5 | PG 已有 `sentences.search_vector` + GIN |
| `summaries_fts` | SQLite FTS5 | PG 已有 `summaries.search_vector` + GIN |

### 2.2 共同表的列差异

| 表 | SQLite 有、PG 无 | PG 有、SQLite 无 |
|---|---|---|
| `experiment_runs` | `actual_json`, `ended_at`, `experiment_id`, `observations`, `owner_user_id`, `planned_json`, `started_at`, `workspace_id` | — |
| `papers` | — | `search_vector` |
| `paragraphs` | — | `search_vector` |
| `sentences` | — | `search_vector` |
| `summaries` | — | `search_vector` |

重要：

```text
PG experiment_runs 不是完整业务表
它缺少 experiment_id / owner_user_id / workspace_id 等关键列
不能直接承接实验功能
```

## 3. 关键发现

### 3.1 PG 已有 FTS 基础，但没有生产验证

PG 索引已存在：

```text
papers_search_idx       GIN(search_vector)
paragraphs_search_idx   GIN(search_vector)
sentences_search_idx    GIN(search_vector)
summaries_search_idx    GIN(search_vector)
```

但生产排序仍走 SQLite：

```text
paragraphs_fts
```

原因：

```text
PG ts_rank 与 SQLite bm25 的排序不等价
尚未做 20-query A/B
```

所以 FTS 不是“从零建设”，而是“验证并切换排序”。

### 3.2 实验与项目是最大 schema 缺口

缺失的不是索引，而是完整业务域：

```text
experiments
experiment_revisions
experiment_signatures
experiment_audit
experiment_access_requests
projects
project_members
```

并且 `experiment_runs` 字段不完整。

### 3.3 sentence_id 是数据一致性前置条件

已确认：

```text
0/17 same ID
17/17 exact text match
```

在纯净化前必须解决，否则跨库证据会错位。

## 4. 目标架构

```text
PostgreSQL
  papers / sections / paragraphs / sentences
  figures / tables
  users / workspaces / memberships
  watch
  reviews / claims / citations
  experiments / projects
  FTS: tsvector + GIN

Chroma
  向量索引，独立保留

文件系统 / 对象存储
  PDF / XML / 图片
```

不在第一阶段强行把 Chroma 放进 PG；如果要求“所有数据一个库”，后续用 pgvector 单独评估。

## 5. 分阶段路线图

### Phase 0：Schema parity（已完成 2026-11-02）

交付：

```text
PG migration:
  projects
  project_members
  experiments
  experiment_revisions
  experiment_signatures
  experiment_audit
  experiment_access_requests
  experiment_runs 补 8 列
```

状态：

```text
PG 67 tables；projects/project_members 已回填
剩余：FTS 4 张 + dual_write_outbox
详情：架构-Phase0-完成记录.md
```

验收：

```text
schema_parity: sqlite_only 只剩 FTS/outbox
所有新表有 PK/FK/索引
SQLite -> PG 回填脚本 dry-run 可重复
```

### Phase 1：实验/项目写路径 PG-primary（进行中）

已完成：

```text
projects 写路径 PG-first：
create / update / add_member / copy
flag: SCIPAL_PROJECT_WRITE_BACKEND=postgres
默认关闭
```

已完成代码：

```text
projects create/update/member/copy
experiments create/update/revision/audit
access requests
signatures
```

待做：

```text
生产 flag canary
```

交付：

```text
projects / experiments services 写 PG
SQLite mirror 可选
```

验收：

```text
创建/修改/删除实验
签名/审计/访问申请
SQLite/PG row count 一致
```

### Phase 2：papers/watch 写路径 PG-primary

交付：

```text
papers workspace / metadata / delete
watch_profiles / runs / items / seen
停用 outbox 依赖
```

验收：

```text
outbox pending = 0 连续 7 天
papers/watch drift = 0
真实 watch run 成功
```

### Phase 3：FTS 切换

交付：

```text
PG paragraph FTS 查询路径
20-query A/B
gold sentence 对齐
```

验收：

```text
Recall@10 >= 1.0000
MRR >= 0.8806
nDCG@10 >= 0.9097
gold sentence >= 12/20
p95 <= 3s
```

不达标不切。

### Phase 4：读路径收口

交付：

```text
paper detail / search / watch / experiments 全部 PG
SQLite 只读
```

验收：

```text
所有 API canary 通过
无 SQLite fallback
回滚演练通过
```

### Phase 5：停 SQLite

交付：

```text
停 dual write
删 outbox
停 SQLite mirror
归档 research.db
```

验收：

```text
PG 备份/恢复演练
连续 7 天无 SQLite 读
回滚镜像可用
```

## 6. 每阶段回滚

```text
Phase 0-1: 保留 SQLite 原表，drop 新 PG 表即可
Phase 2: 恢复 SCIPAL_*_WRITE_BACKEND，重启旧镜像
Phase 3: 恢复 SQLITE_FTS 开关，保留 PG 索引
Phase 4: 回滚 app 镜像 + 恢复 SQLite 读
Phase 5: 保留 research.db 只读副本
```

## 7. 不能跳过的门

```text
sentence_id 稳定
experiment_runs schema 完整
FTS 指标对齐
p95 <= 3s
outbox/drift 清零
备份/恢复演练
```

## 8. 建议的立即动作

```text
1. 补 PG 缺失表 + experiment_runs 列（Phase 0）
2. 写 SQLite -> PG 回填脚本
3. 修 sentence_id 稳定键
4. 做 PG paragraph FTS 20-query A/B
5. 再决定是否继续 Phase 1
```

在 Phase 0 完成前，不应开启“停 SQLite”或“删除 outbox”。

## 9. 暂缓的检索实验

段落-句子双权重重排已有设计，但**暂缓到纯净化完成之后**：

```text
 docs/检索-段句双权重实验设计.md
```

原因：

```text
1. 需要同一数据库内同时取 paragraph 和 sentence
2. sentence_id 必须先稳定
3. PG FTS 切换会改变基线，提前调参没有意义
```
