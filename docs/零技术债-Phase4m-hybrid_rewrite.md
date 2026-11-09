# 零技术债 Phase 4m：HybridSearch 单轨化（重写）

> 日期：2026-11-09  
> 状态：**删除 Chroma / SQLite 路径，保留 pgvector + ParadeDB/PG FTS**

---

## 1. 重写理由

生产实际只用：

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_FTS_BACKEND=postgres
SCIPAL_FTS_PARADEDB_PERCENT=100
SCIPAL_SEARCH_META_BACKEND=postgres
```

旧实现仍保留：

```text
Chroma client / collections
SQLite conn
SQLite FTS fallback
```

31 处内部属性引用，逐段迁移只会得到“PG 主路径 + 死分支”。

---

## 2. 新结构

```text
HybridSearch
  __init__      无 SQLite / Chroma
  vector_search pgvector only
  fts_search    ParadeDB / PG FTS only
  _get_filtered_paper_ids -> PG
  _paper_row    -> PG
  search_papers -> paragraph 聚合
  figures / tables / chunks -> []
```

保留：

```text
RRF / multi-query / dynamic weights
MMR / dedup / diagnostics
```

---

## 3. 行为

生产 pgvector 下旧实现本来：

```text
figures = []
tables = []
chunks = []
papers = paragraph 聚合
```

新实现保持相同返回。

---

## 4. 测试

```text
test_hybrid_env
test_hybrid_filter
test_hybrid_fts_routing
test_hybrid_retriever_shared
test_shared_hybrid
9 passed
```

`percent=0` 路由测试改为 PG FTS 空结果，不再期待 SQLite 异常。

---

## 5. Allowlist

```text
24 -> 23
```

---

## 6. 验证门槛

合并部署后必须跑：

```text
20 题：Recall@10 >= 0.675，nDCG@10 >= 0.461
SciFact 300：>= 0.8669 / 0.7458
A/B：0 5xx
```

任何一项下降立即回滚。
