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

## 7. 下一步

```text
G3.6a PG read adapter
```

先读后写，避免权限语义半迁移。
