# Phase 0 完成记录：Schema Parity

> 日期：2026-11-02  
> 结果：Schema 对齐完成；剩余差异仅为 FTS 与 outbox。

## 1. 迁移内容

新增 PG 表：

```text
projects
project_members
experiments
experiment_revisions
experiment_signatures
experiment_audit
experiment_access_requests
```

补齐 `experiment_runs`：

```text
experiment_id
workspace_id
owner_user_id
planned_json
actual_json
observations
started_at
ended_at
```

文件：

```text
build_db/migrations/20261102_phase0_parity.sql
scripts/apply_pg_migration.py
scripts/backfill_phase0.py
```

## 2. 生产执行

Schema 备份：

```text
G:\sciPal_deploy\backups\scipal_bench_schema_before_phase0_20261102.sql
```

应用：

```text
statements = 25
applied    = true
```

回填：

| 表 | SQLite | PG inserted |
|---|---:|---:|
| projects | 1 | 1 |
| project_members | 2 | 2 |
| experiments | 0 | 0 |
| experiment_revisions | 0 | 0 |
| experiment_signatures | 0 | 0 |
| experiment_audit | 0 | 0 |
| experiment_access_requests | 0 | 0 |
| experiment_runs | 0 | 0 |

验证：

```text
PG projects          1
PG project_members    2
experiment_runs cols 19
```

## 3. Schema 对比

```text
SQLite 应用表   72
PG 表           67
共同表          67
PG-only          0
SQLite-only      5
```

剩余 SQLite-only：

```text
dual_write_outbox
papers_fts
paragraphs_fts
sentences_fts
summaries_fts
```

列差异：

```text
papers.search_vector
paragraphs.search_vector
sentences.search_vector
summaries.search_vector
```

这些是 Phase 3 FTS 的工作，不是 Phase 0 遗留。

## 4. 生产状态

```text
app          healthy
/api/health  200
PG           67 tables
```

未改应用读写路径；Phase 0 只做 schema + 回填。

## 5. 回滚

迁移是 additive：

```text
新增表可 DROP
experiment_runs 新增列可保留或 DROP COLUMN
schema 备份可用于对照
```

没有删除 SQLite 表，也没有改 outbox。

## 6. 测试

```text
tests/test_phase0_migration.py
  3 tests OK
```

## 7. 下一步

Phase 1：

```text
projects / experiments 写路径 PG-primary
```

前置：

```text
确认服务层使用的 SQLite 写入点
为 projects/experiments 加 PG 写 helper
保持 SQLite mirror 直到验收
```
