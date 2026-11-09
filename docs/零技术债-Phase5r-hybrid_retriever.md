# 零技术债 Phase 5r：hybrid retriever local index PG-only

> 日期：2026-11-09  
> 状态：**本地论文索引读取固定 PG**

---

## 1. 改动

```text
services/search/hybrid_retriever.py
  sqlite3 删除
  _load_local_paper_index -> PG papers
```

---

## 2. 验证

```text
hybrid retriever shared   1 passed
allowlist                 9 -> 8
```

---

## 3. 下一步

```text
services/search/ingest.py
services/search/online_downloader.py
```

两者仍需 family 级迁移。
