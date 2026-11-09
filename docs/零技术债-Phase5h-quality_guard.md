# 零技术债 Phase 5h：quality guard PG-only

> 日期：2026-11-09  
> 状态：**FtsLanding 不再读 SQLite**

---

## 1. 改动

```text
services/quality/guard.py
  sqlite3 / threading.local 删除
  FtsLanding -> PG paragraphs.search_vector
```

生产 guard 以前在 `research.db` 退役后会把所有 term 判为未落地；现在查 PG。

---

## 2. 测试

```text
test_guard           15 passed
allowlist            19 -> 18
```

---

## 3. 下一步

```text
services/query/search_service.py
```
