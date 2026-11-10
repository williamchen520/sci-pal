# 零技术债 Phase 6c：experiments PG-only

> 日期：2026-11-10  
> 状态：**运行时 PG facade + 测试 SQLite provider**

---

## 1. 结构

```text
services/experiments/service.py     facade -> pg_read / pg_write
services/experiments/runs.py        facade -> pg_runs
services/experiments/pg_service.py  PG 适配
services/experiments/model.py       常量 / 快照 / hash

tests/support/experiments_sqlite.py
tests/support/experiments_runs_sqlite.py
```

## 2. 测试

```text
test_experiments_routes + access + runs   17 passed
allowlist                                 5 -> 3
```

## 3. 边界

```text
生产：pg_read/pg_write/pg_runs
测试：SQLite provider
路由 import 名不变
```
