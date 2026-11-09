# 零技术债 Phase 5o：retrieval nodes PG-only

> 日期：2026-11-09  
> 状态：**段落节点读取固定 PG**

---

## 1. 改动

```text
services/search/retrieval_nodes.py
  sqlite3 删除
  paragraph_nodes -> PG paragraphs WHERE section_id = ANY(%s)
```

---

## 2. 测试

```text
test_retrieval_nodes   2 passed
allowlist              12 -> 11
```

---

## 3. 下一步

```text
services/search/ingest.py
```
