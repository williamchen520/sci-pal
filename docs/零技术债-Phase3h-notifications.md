# 零技术债 Phase 3h：notifications 切 PG-only

> 日期：2026-11-09  
> 状态：**review webhooks 删除 SQLite fallback**

---

## 1. 改动

```text
services/review/notifications.py
  sqlite3 -> _pg()
  _sqlite_allowed 删除
  _pg_enabled 删除
  add/list/delete/notify 全部只走 PostgreSQL
```

`conn` / `db_path` 参数保留，仅兼容调用方。

---

## 2. 原因

```text
webhook 表已迁入租户 schema
生产 SCIPAL_REVIEW_WEBHOOKS_ALLOW_SQLITE 从未开启
```

---

## 3. 测试

```text
tests/test_webhooks.py
  旧：SQLite migrate + systematic
  新：fake PG + 过滤/删除断言
```

结果：

```text
3 passed
```

---

## 4. Allowlist

```text
49 -> 48
```

---

## 5. Batch 4 拆分

```text
notifications      完成
task_manager       待做
claims/service     待做
notes/service      待做
```

原因：

```text
后三个的测试仍用 SQLite service 断言
需要先迁移测试契约
```

---

## 6. 下一步

```text
task_manager
只保留 PGTaskManager，删除 SQLite TaskManager
```
