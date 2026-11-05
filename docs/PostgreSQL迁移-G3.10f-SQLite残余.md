# G3.10f SQLite 残余清单

> 日期：2026-11-05  
> systematic review 已切 PG，剩余模块如下

---

## 1. 已完成 PG

```text
core ingest
projects
protocols
claims
experiments
experiment_runs
notes
audit
reviews
review systematic（含 screening/evidence/reports）
```

---

## 2. 仍写 SQLite

| 模块 | 数据 | 约 |
|---|---|---|
| review tasks | tasks | 477 |
| references / library | 文献库 | 待盘 |
| qa citations | 引用缓存 | 待盘 |
| watch | 监测 | 待盘 |
| tenancy 边缘 | memberships 等 | 待盘 |

---

## 3. 不能设只读

```text
tasks 在请求内持续更新进度
references / qa 仍写 SQLite
```

`PRAGMA query_only=ON` 仍会 500。

---

## 4. 建议顺序

```text
G3.10f1 review tasks PG
G3.10f2 references/library PG
G3.10f3 qa citations PG
G3.10f4 watch PG
G3.10f5 SQLite 只读
```

---

## 4b. G3.10f1 tasks PG

```text
services/review/pg_tasks.py
  PGTaskManager
SCIPAL_REVIEW_TASKS_BACKEND=postgres
```

同步：

```text
tasks 477/477
```

冒烟：

```text
create / get / complete ✅
```

## 4c. G3.10f2 reference library PG

```text
services/references/library.py
  SCIPAL_REFERENCE_LIBRARY_BACKEND=postgres
```

冒烟：

```text
count 1
list 1
import 1
cleanup ✅
```

## 4d. reference library 切流

```text
SCIPAL_REFERENCE_LIBRARY_BACKEND=postgres
```

冒烟：

```text
count 1
list 1
api 1
```

## 4e. G3.10f3 qa citations

```text
services/qa/citations.py
  SCIPAL_QA_CITATIONS_BACKEND=postgres
```

只读查询，不写 SQLite。

冒烟：

```text
para -> 8 sentence ids
```

## 4f. G3.10f4 watch read

```text
services/watch/pg_read.py
  profiles / runs / items
SCIPAL_WATCH_BACKEND=postgres
```

冒烟：

```text
profiles 1
get      HCC 免疫治疗
runs     9
```

写路径仍 SQLite，默认关闭。

## 4g. qa/watch 切流

```text
SCIPAL_QA_CITATIONS_BACKEND=postgres
SCIPAL_WATCH_BACKEND=postgres
```

冒烟：

```text
qa 8 sentence ids
watch profiles 1 / runs 9
```

## 5. 当前生产

```text
review systematic   PG
reviews             PG
protocols           PG
projects            PG
tasks/references    SQLite
app                 healthy
```
