# 零技术债 Phase 5j：context expander PG-only

> 日期：2026-11-09  
> 状态：**生产固定 PGReadCompat，测试注入 SQLite conn**

---

## 1. 改动

```text
services/search/context_expander.py
  sqlite3 删除
  __init__(db_path, conn=None)
    conn 注入 -> 测试
    默认     -> PGReadCompat
```

这样不破坏已有的 SQLite fixture 测试。

---

## 2. 测试

```text
test_context_expander   2 passed
allowlist               17 -> 16
```

---

## 3. 下一步

```text
services/search/graph_traverser.py
```
