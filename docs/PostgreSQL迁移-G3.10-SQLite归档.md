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

## 4b. G3.10b audit PG

```text
services/data_sandbox/audit.py
  SCIPAL_AUDIT_BACKEND=postgres
```

修复：

```text
data_audit identity sequence 落后
setval -> max(id)+1
```

冒烟：

```text
list 1
SQLite audit 40 -> 40
cleanup ✅
```

测试：

```text
tests.test_audit_pg 2 OK
```

## 4c. audit 切流

```text
SCIPAL_AUDIT_BACKEND=postgres
```

冒烟：

```text
list 1
SQLite audit 40 -> 40
cleanup ✅
```

## 4d. G3.10c experiment_runs PG

```text
services/experiments/pg_runs.py
  list/create/get/update
SCIPAL_RUNS_BACKEND=postgres
```

测试：

```text
tests.test_runs_pg 2 OK
```

默认关闭。

## 4e. runs 切流

```text
SCIPAL_RUNS_BACKEND=postgres
```

冒烟：

```text
create run
list 1
update completed
cleanup ✅
```

## 4f. G3.10d FTS trigger 评估

现状：

```text
FTS triggers 12 保留
SQLite 核心写入已停止
trigger 实际不再触发
```

结论：

```text
保留 trigger 作为回退表定义
不删除
直到 SQLite FTS 回退退役
```

新论文只进 PG，SQLite FTS 回退本身已不覆盖新论文。

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
