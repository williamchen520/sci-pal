# 零技术债 Phase 3：删除 watch pg_sync

> 日期：2026-11-08  
> 状态：**第一个存量 SQLite fallback 已删除**

---

## 1. 删除对象

```text
services/watch/pg_sync.py
tests/test_watch_pg_sync.py
```

原因：

```text
watch 已使用 SCIPAL_WATCH_PG_STORE=1
PG store 直接写 PostgreSQL
pg_sync 只是 SQLite outbox 补写
```

---

## 2. 代码改动

```text
services/watch/runner.py
  - remove import sync_watch_pending
  - remove sync_watch_pending(db_path) call
```

---

## 3. Allowlist

```text
62 -> 61
```

audit：

```text
SQLITE_ALLOWLIST_UPDATED 61
```

---

## 4. 验证

```text
tests.test_watch_pg_store     2 passed
sqlite group                 37 passed
```

watch 生产路径：

```text
SCIPAL_WATCH_PG_STORE=1
-> pg_store
-> no SQLite sync
```

---

## 5. 影响

```text
SQLite watch 模式不再有 PG catch-up
但生产不使用该模式
```

---

## 6. 下一步

```text
继续从 61 个文件里删下一个
优先无租户写路径、无核心测试的模块
```
