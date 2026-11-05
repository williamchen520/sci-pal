# G3.10 SQLite 归档盘点

> 日期：2026-11-05  
> 结论：先备份，暂不设只读

---

## 1. 归档

```text
G:/sciPal_deploy/backups/research_g3_10_20261105.db
size 1752.1 MB
integrity ok
```

---

## 2. 已迁 PG

```text
claims
experiments
notes
core ingest: papers/sections/paragraphs/sentences/figures/tables/citations/links
```

dualwrite trigger：

```text
27 -> 0
```

outbox：

```text
pending 0
```

---

## 3. SQLite 仍活跃

| 功能 | 原因 |
|---|---|
| FTS triggers | SQLite FTS 回退仍保留 |
| data_sandbox audit | 仍 SQLite |
| experiment_runs | 仍 SQLite |
| 部分 legacy 脚本 | 非请求主路径 |

因此现在设置：

```text
PRAGMA query_only=ON
```

会破坏 FTS 回退和 audit/runs。

---

## 4. 正确顺序

```text
G3.10a 备份归档（完成）
G3.10b data_sandbox audit -> PG
G3.10c experiment_runs -> PG
G3.10d 停 FTS trigger / 评估回退
G3.10e SQLite 只读
```

---

## 5. 当前生产

```text
claims        PG
experiments   PG
notes         PG
core ingest   PG-only
FTS           100% ParadeDB
Vector        Chroma
SQLite        仍可写（FTS/audit/runs）
app           healthy
```
