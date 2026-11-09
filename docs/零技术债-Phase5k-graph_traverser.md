# 零技术债 Phase 5k：graph traverser PG-only

> 日期：2026-11-09  
> 状态：**GraphTraverser 固定 PGReadCompat**

---

## 1. 改动

```text
services/search/graph_traverser.py
  sqlite3 删除
  固定 PGReadCompat
```

生产本来已走 PG 分支；本次删除 SQLite fallback。

---

## 2. 验证

```text
graph traverser pg + papers routes   8 passed
allowlist                            16 -> 15
```

---

## 3. 下一步

```text
services/search/tree_context.py
```
