# 零技术债 Phase 4e：watch family 注入完成

> 日期：2026-11-09  
> 状态：**repo SQLite 移入 tests；生产固定 pg_store**

---

## 1. 生产

```text
services/watch/repo.py
  只剩 now_iso
  所有 SQLite 仓储删除

services/watch/runner.py
  _store() 固定 pg_store
  run_profile(..., store=None) 支持注入

services/watch/scheduler.py
  run_due(..., profiles=None)
  不再 repo.connect fallback

routes/watch.py
  build_watch_blueprint(..., store=None, run_profile=None)
  默认 pg_store
```

---

## 2. 测试

```text
tests/support_sqlite_watch_repo.py
  原 SQLite repo
```

注入：

```text
test_watch          runner._store patch
test_watch_routes   blueprint store=repo
test_watch_scheduler profiles=due_profiles(conn)
test_watch_runner_store 只断言 pg_store
```

结果：

```text
watch 4 files   14 passed
```

---

## 3. Allowlist

```text
28 -> 27
```

---

## 4. 下一步

```text
services/watch/pg_writes.py
services/watch/repo.py 已清
```

剩余 watch 的 pg_writes 里还有 SQLite fallback。
