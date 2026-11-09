# 零技术债 Phase 4c：tenancy scoping PG-only

> 日期：2026-11-09  
> 状态：**allowed_paper_ids 不再读 SQLite**

---

## 1. 问题

```text
allowed_paper_ids 只查 research.db
research.db 已退役
生产会返回空集合
```

这会让 QA/search 的 workspace scoping 过度拒绝。

---

## 2. 改动

```text
services/tenancy/scoping.py
  sqlite3 / PRAGMA / ALTER 删除
  allowed_paper_ids 固定 PG public.papers
```

---

## 3. 测试

```text
ScopingTests
  fake main_read_connection

QAScopingRouteTests
  patch routes.qa.allowed_paper_ids 为 SQLite 测试夹具
```

结果：

```text
4 passed
```

---

## 4. Allowlist

```text
30 -> 29
```

---

## 5. 下一步

```text
services/tenancy/service.py
```

继续 tenancy 边界。
