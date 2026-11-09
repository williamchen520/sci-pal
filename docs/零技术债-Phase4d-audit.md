# 零技术债 Phase 4d：data sandbox audit PG-only

> 日期：2026-11-09  
> 状态：**audit 删除 SQLite**

---

## 1. 改动

```text
services/data_sandbox/audit.py
  sqlite3 / _connect / _pg_backend / SCHEMA 删除
  log_event / list_events 固定 pg_connection
```

生产本来就是：

```text
SCIPAL_AUDIT_BACKEND=postgres
```

---

## 2. 测试

```text
test_audit_pg
  已有 fake PG

test_data_e2e
  audit.log_event / list_events 用内存替身
```

结果：

```text
4 passed
```

---

## 3. Allowlist

```text
29 -> 28
```

---

## 4. 下一步

```text
services/watch/repo.py family
```

或 protocols/systematic 大 family。
