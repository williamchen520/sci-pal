# 零技术债 Phase 4b：tenancy permissions PG-only

> 日期：2026-11-09  
> 状态：**permissions.audit 删除 SQLite fallback**

---

## 1. 改动

```text
services/tenancy/permissions.py
  sqlite3 删除
  audit 固定 pg_writes.audit_event
  db_path 保留兼容
```

---

## 2. 验证

```text
tenancy / tenancy routes / pg writes   25 passed
allowlist                               31 -> 30
```

---

## 3. 下一步

```text
services/tenancy/scoping.py
services/tenancy/service.py
```

继续 tenancy 边界。
