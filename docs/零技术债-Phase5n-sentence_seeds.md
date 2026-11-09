# 零技术债 Phase 5n：sentence seeds PG-only

> 日期：2026-11-09  
> 状态：**句子 FTS 种子固定 PG**

---

## 1. 改动

```text
services/search/sentence_seeds.py
  sqlite3 / sentences_fts 删除
  PG sentences.search_vector + to_tsquery
  GROUP BY para_id，rank DESC
```

---

## 2. 测试

```text
test_sentence_seeds   2 passed
allowlist             13 -> 12
```

---

## 3. 下一步

```text
services/search/retrieval_nodes.py
```
