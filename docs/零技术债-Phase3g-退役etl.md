# 零技术债 Phase 3g：退役 etl

> 日期：2026-11-09  
> 状态：**etl 及离线迁移脚本删除**

---

## 1. 删除

```text
services/db/etl.py
tests/test_pg_etl.py
```

依赖脚本：

```text
scripts/create_pg_v2.py
scripts/fts_alignment.py
scripts/pg_etl.py
scripts/rebuild_fts_porter.py
```

---

## 2. 原因

```text
ETL 是 SQLite -> PostgreSQL 的历史迁移工具
PG-only 后不再需要
```

`services/db/__init__.py` 现在只保留：

```text
read_router
```

---

## 3. Allowlist

```text
50 -> 49
SQLITE_ALLOWLIST_OK 49
```

---

## 4. 测试

```text
read_router / tenancy_scoping   8 passed
sqlite group                   37 passed
```

---

## 5. 当前

```text
运行时 SQLite 硬禁
dual_write / health-cron 删除
etl 删除
allowlist 49
```

---

## 6. 下一步

```text
继续清剩余 49 个 connect
优先离线/审计
```
