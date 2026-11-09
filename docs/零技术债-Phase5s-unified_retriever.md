# 零技术债 Phase 5s：unified retriever PG-only

> 日期：2026-11-09  
> 状态：**unified retriever 不再读 SQLite**

---

## 1. 改动

```text
services/search/unified_retriever.py
  sentence seed 回填 -> PG
  summary section 映射 -> PG
  to_evidence_json 元数据 -> PGReadCompat（删除 SQLite 分支）
  sqlite3 / STRUCT_DB 删除
```

排序与检索链不变，仅替换元数据/段落读取。

## 2. 测试

```text
search hybrid routes + hybrid retriever + context expander   8 passed
allowlist                                                    8 -> 7
```

搜索路由测试补 mock `allowed_paper_ids`（该函数已 PG-only）。

## 3. 下一步

```text
services/search/ingest.py
services/search/online_downloader.py
```

两者仍是 family 级。
