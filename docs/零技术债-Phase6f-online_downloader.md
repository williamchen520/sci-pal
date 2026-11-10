# 零技术债 Phase 6f：online downloader PG-only

> 日期：2026-11-10  
> 状态：**下载后写入和增量索引固定 PG**

---

## 1. 改动

```text
services/search/online_downloader.py
  _import_new_papers -> paper_pg_writes only
  _incremental_index -> pgvector paragraph_embeddings
  Chroma / SQLite 删除
```

## 2. 验证

```text
test_papers_downloads_routes   7 passed
allowlist                      2 -> 1
```

`allowlist` 只剩：

```text
services/search/hybrid_search.py（明确保留的旧引擎）
```

## 3. 结论

PG-only 运行时清理完成；旧检索引擎按计划保留为 fallback。
