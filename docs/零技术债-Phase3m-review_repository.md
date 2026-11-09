# 零技术债 Phase 3m：review_repository PG-only

> 日期：2026-11-09  
> 状态：**生产 ReviewRepository 固定 PG；SQLite 实现移入 tests**

---

## 1. 生产

```text
services/review/review_repository.py
  sqlite3 / SCHEMA / _session / _connect 删除
  save/get/list 固定 _pg()
  ensure_schema no-op
  db_path 保留兼容
```

---

## 2. 测试支撑

```text
tests/support_sqlite_review_repository.py
  SqliteReviewRepository
```

只给单元测试建临时库用，不进入 services。

---

## 3. 注入

```text
routes/reviews.py
  repository_factory=ReviewRepository
```

```text
services/workflow/stages.py
  context.services["review_repository_factory"]
```

默认仍是 PG；测试传 SQLite helper。

---

## 4. reference_link

PG 不可用时不再抛：

```text
try main_read_connection()
except -> pg=None
仍补 doi_url
跳过 paper_id
```

这样离线 workflow 测试不会因数据库不可用失败。

---

## 5. 验证

```text
review_repository / reviews_routes / workflow_stages
  passed

sqlite group
  37 passed

allowlist
  44 -> 43
```

---

## 6. 下一步

`references/library` 用同样模式：

```text
生产 PG
SQLite 移到 tests/support
路由注入
```
