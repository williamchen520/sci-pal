# 零技术债 Phase 5l：tree_context PG-only

> 日期：2026-11-09  
> 状态：**TreeContextBuilder 生产固定 PGReadCompat**

---

## 1. 改动

```text
services/search/tree_context.py
  sqlite3 删除
  __init__(db_path, conn_factory=None)
    生产 -> PGReadCompat
    测试 -> 注入 SQLite factory
```

---

## 2. 测试

```text
test_tree_context   2 passed
allowlist           15 -> 14
```

---

## 3. 下一步

```text
services/search/tree_router.py
```
