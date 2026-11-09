# 零技术债 Phase 4f：watch delete PG-only

> 日期：2026-11-09  
> 状态：**watch 删除占位论文不再写 SQLite**

---

## 1. 改动

```text
services/watch/pg_writes.py
  delete_paper_best_effort
    PG DELETE RETURNING
    删除 SQLite outbox 写入
  sqlite3 删除
```

---

## 2. 原因

```text
watch repo 已退出生产
PG 删除失败直接 WatchWriteError
不再需要 SQLite outbox
```

---

## 3. 验证

```text
watch 4 个测试文件   14 passed
allowlist            27 -> 26
```

---

## 4. 下一步

```text
services/watch 已无 SQLite
```

剩余列表回到核心检索 / protocols / systematic。
