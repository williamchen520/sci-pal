# 零技术债 Phase 6a：projects PG-only

> 日期：2026-11-10  
> 状态：**projects 运行时固定 pg_service**

---

## 1. 改动

```text
routes/projects.py
  backend 注入，默认 services.projects.pg_service
  删除 SQLite service 分支

services/projects/service.py
  移出运行时 -> tests/support/projects_sqlite.py

services/projects/__init__.py
  导出 pg_service
```

## 2. 测试

```text
tests/test_projects_routes.py
  注入 SqliteProjects，保留原有 SQLite fixture

test_projects_routes + test_projects_pg   6 passed
allowlist                                 7 -> 6
```

## 3. 边界

```text
production: project_pg
tests:      SqliteProjects（显式注入）
```

`service.py` 不再位于 `services/`，不会进入运行时导入链。
