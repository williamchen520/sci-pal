# 零技术债 Phase 6e：ingest 数据写入 PG-only

> 日期：2026-11-10  
> 状态：**运行时 `_write_batch` 只走 PG，SQLite writer 移到测试**

---

## 1. 改动

```text
services/search/ingest.py
  _write_batch -> PG only
  _write_batch_sqlite -> 测试 writer 调用
  _run 不再无条件 sqlite3.connect
  _connect 委托 writer（只测试）

services/search/ingest_writer.py        writer factory
tests/support/ingest_sqlite_writer.py   SQLite writer
tests/__init__.py                       注入 writer
```

## 2. 边界

```text
生产：
  paper_pg_writes.write_papers_batch
  pgvector embeddings

测试：
  SqliteIngestWriter -> _write_batch_sqlite
```

## 3. 验证

```text
test_ingest   11 passed
allowlist     3 -> 2
```

## 4. 剩余

```text
online_downloader.py
hybrid_search.py（旧引擎保留）
```
