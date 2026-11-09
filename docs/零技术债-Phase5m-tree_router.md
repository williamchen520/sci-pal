# 零技术债 Phase 5m：tree router PG-only

> 日期：2026-11-09  
> 状态：**TreeRouter 生产固定 PGReadCompat**

---

## 1. 改动

```text
services/search/tree_router.py
  sqlite3 删除
  __init__(..., conn_factory=None)
    生产 -> PGReadCompat
    测试 -> SQLite factory
```

---

## 2. 测试

```text
test_tree_router   1 passed
allowlist          14 -> 13
```

---

## 3. 下一步

```text
services/search/sentence_seeds.py
```
