# 零技术债 Phase 5p：papers pg_writes PG-only

> 日期：2026-11-09  
> 状态：**paper metadata 写入不再 mirror SQLite**

---

## 1. 改动

```text
services/papers/pg_writes.py
  update_workspace 删除 SQLite mirror
  update_metadata_if_exists 删除 SQLite mirror
```

测试 mock 目标从过期的 `_pg_connection` 改为 `_ingest_connection`。

---

## 2. 验证

```text
test_paper_pg_writes   7 passed
allowlist              11 -> 10
```

---

## 3. 下一步

```text
services/workflow/stages.py
```
