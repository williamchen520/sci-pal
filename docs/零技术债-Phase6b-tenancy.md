# 零技术债 Phase 6b：tenancy PG-only

> 日期：2026-11-10  
> 状态：**运行时 PG facade + 测试 SQLite provider**

---

## 1. 架构

```text
routes / api_server
  -> services.tenancy.service（facade）
       default -> services.tenancy.pg_service
       tests   -> tests.support.tenancy_sqlite
```

为什么用 facade：

```text
tenancy 被 projects/experiments/notes/papers/runs 多处直接 import
逐路由注入 backend 会扩散到所有模块
facade 保持 import 名不变，只在调用时分派
```

## 2. 改动

```text
services/tenancy/service.py        facade
services/tenancy/pg_service.py     PG 实现
services/tenancy/service.py(old)   -> tests/support/tenancy_sqlite.py

tests/__init__.py                  configure(sqlite) + test audit
tests/test_experiments_*.py        注入 SqliteProjects
tests/test_multiuser_e2e.py        注入 SqliteProjects
tests/test_pi_copy.py              注入 SqliteProjects
tests/test_runs_routes.py          注入 SqliteProjects
```

## 3. 验证

```text
test_tenancy + routes + pg_writes + projects + pi_copy
  32 passed

allowlist 6 -> 5
```

已知不在本次范围：

```text
test_papers_isolation / multiuser 的 papers 断言行
仍依赖 papers 路由 SQLite，而 papers 早已 PG-only
```

## 4. 边界

```text
生产：pg_service
测试：SQLite provider
扩展句/业务不改
```
