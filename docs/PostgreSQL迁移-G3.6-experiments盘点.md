# G3.6 experiments 盘点

> 日期：2026-11-05  
> 结论：experiments 与 claims 类似，PG 仅写 mirror，读路径仍全 SQLite

---

## 1. 当前结构

```text
routes/experiments.py
  -> service.list/get/create/update/...
  -> SQLite connection
```

PG 写：

```text
services/experiments/pg_writes.py
  create_experiment
  update_experiment
  create_access_request
  decide_access_request
  create_signature
```

---

## 2. 路由

| 路由 | 类型 | PG |
|---|---|---|
| GET projects/<id>/experiments | 读 | ❌ |
| POST projects/<id>/experiments | 写 | 🟡 mirror |
| GET experiments/<id> | 读 | ❌ |
| PUT experiments/<id> | 写 | 🟡 mirror |
| GET revisions | 读 | ❌ |
| GET audit | 读 | ❌ |
| POST sign | 写 | 🟡 mirror |
| GET signatures | 读 | ❌ |
| access-requests | 读写 | 🟡 mirror |

---

## 3. 关键依赖

实验权限不是简单 SQL：

```text
_project_access
_active_approval
audit()
revision hash
```

这些语义都在 SQLite service 里，必须一起迁，不能只换 SQL。

---

## 4. 子任务

```text
G3.6a PG read adapter
  list_experiments
  get_experiment
  revisions
  audit

G3.6b PG write adapter
  create_experiment
  update_experiment
  sign_experiment
  access requests

G3.6c 路由切换
  SCIPAL_EXPERIMENTS_BACKEND=postgres

G3.6d 冒烟
  create/update/sign/access
```

---

## 5. 验收

```text
1. 新实验只写 PG
2. revision / audit 顺序一致
3. 权限与 approval 语义一致
4. SQLite 实验表不增长
5. 路由测试全绿
```

---

## 6. 当前生产

```text
experiments 仍 SQLite primary
PG mirror 继续
app healthy
```

---

## 6b. G3.6a 完成

```text
services/experiments/pg_read.py
  list_experiments
  get_experiment
  list_revisions
  get_audit
  list_signatures
  list_access_requests
  list_workspace_requests
```

路由：

```text
SCIPAL_EXPERIMENTS_BACKEND=postgres
```

冒烟：

```text
list 1 / get true / revisions 1 / audit 1
```

权限：

```text
PG memberships / projects / project_members
```

## 6c. G3.6b 进行中

已完成：

```text
create_experiment PG-only
  experiment + revision + audit
路由 POST /api/projects/<id>/experiments
```

测试：

```text
tests.test_experiments_pg_write 2 OK
全量 891 tests OK
```

已完成：

```text
update_experiment
sign_experiment
```

仍需：

```text
access requests
```

## 7. 下一步

```text
G3.6a PG read adapter
```

先读后写，避免权限语义半迁移。
