# G3.10e 剩余 SQLite 写入盘点

> 日期：2026-11-05  
> 结论：**不设置 query_only**，SQLite 仍有多个主写入模块

---

## 1. 已迁 PG

```text
claims
experiments
experiment_runs
notes
data_audit
core ingest
```

---

## 2. 仍以 SQLite 为主

| 模块 | 代表写入 | 风险 |
|---|---|---|
| projects | projects / project_members | 项目创建/更新 |
| protocols | protocol_steps / runs / files | 方案与运行文件 |
| review | review_projects / screening / adjudications / evidence_rows | 系统综述 |
| review tasks | tasks | 异步任务状态 |
| review risk | risk_of_bias | 偏倚评估 |
| references | library | 文献库 |
| qa citations | citations | 引用缓存 |

SQLite 写语句数量：

```text
> 100 处
```

---

## 3. 为什么不能只读

这些功能在 HTTP 请求内直接写 SQLite：

```text
创建项目
保存 protocol step
筛选/裁决
生成证据表
任务进度
```

设置：

```text
PRAGMA query_only=ON
```

会立即导致这些接口 500。

---

## 4. 可行路线

### A. 继续逐模块迁 PG

```text
G3.10e1 projects
G3.10e2 protocols
G3.10e3 review projects
G3.10e4 review tasks
G3.10e5 references
```

### B. 冻结 SQLite 功能

```text
仅保留现有只读
新写入返回 503
```

### C. 暂不追求只读

```text
SQLite 继续作为功能库
PG 作为检索/核心数据
```

---

## 5. 建议

```text
不设 query_only
不删 FTS trigger
先决定：继续迁 review/projects，还是暂停 SQLite 只读目标
```

---

## 5b. G3.10e1 projects

```text
services/projects/pg_service.py
  list/get/create/update/add_member
routes/projects.py
  SCIPAL_PROJECTS_BACKEND=postgres
```

冒烟：

```text
list 1
create / get / update / add_member ✅
cleanup ✅
```

copy_project 已补：

```text
pg_service.copy_project
```

测试：

```text
tests.test_projects_pg 2 OK
```

## 5c. projects 切流

```text
SCIPAL_PROJECTS_BACKEND=postgres
```

冒烟：

```text
list 1
get HBV
create / update / add_member
copy_project ✅
cleanup ✅
```

已知缺口：

```text
copy_project 未写 workspace audit
```

## 5d. review repository PG

```text
services/review/review_repository.py
  SCIPAL_REVIEWS_BACKEND=postgres
```

数据：

```text
reviews 29 / 29
```

冒烟：

```text
list 5
save / get
cleanup ✅
```

仍未迁移：

```text
review_projects
screening_decisions
evidence_rows
tasks
```

## 6. 当前生产

```text
core/claims/experiments/notes/runs/audit   PG
review/projects/protocols                 SQLite
FTS                                       100% ParadeDB
Vector                                    Chroma
app                                       healthy
```
