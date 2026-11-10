# 零技术债 Phase 6d：ingest task store PG

> 日期：2026-11-10  
> 状态：任务状态 PG，数据写入仍保留原路径

---

## 1. 范围

只迁移 `ingest_tasks`：

```text
start
status
cancel
execute
set
cancelled
```

未动：

```text
下载
JATS 解析
论文写入
Chroma / pgvector
```

## 2. 结构

```text
services/search/ingest_tasks.py       PG store
tests/support/ingest_tasks_sqlite.py  SQLite provider
services/search/ingest.py             通过 task_store_for 分派
```

## 3. 验证

```text
test_ingest   11 passed
```

## 4. 后续

```text
6e: 数据写入 PG-only / Chroma 边界
```
