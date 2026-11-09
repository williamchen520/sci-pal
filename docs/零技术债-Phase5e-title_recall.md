# 零技术债 Phase 5e：title recall PG-only

> 日期：2026-11-09  
> 状态：**标题召回固定 PG**

---

## 1. 改动

```text
services/review/title_recall.py
  sqlite3 / papers_fts / abstracts.db 删除
  papers 标题 FTS -> PG to_tsvector/to_tsquery
  abstracts 标题+摘要 FTS -> PG abstracts
  best_paragraphs -> PG paragraphs
```

---

## 2. 测试

```text
test_title_recall   4 passed
allowlist           22 -> 21
```

测试改为 fake PG，不再建 SQLite FTS。

---

## 3. 下一步

```text
services/review/review_generator.py
```
