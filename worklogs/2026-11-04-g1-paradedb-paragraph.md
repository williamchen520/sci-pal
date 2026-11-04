# Worklog: G1.1 ParadeDB 段落适配

> 日期：2026-11-04  
> PR：Pending Review

## 1. 改动

```text
services/search/pg_fts.py
  ParadeDBParagraphFTS

services/search/hybrid_search.py
  SCIPAL_FTS_BACKEND=paradedb
  _paradedb_fts_search

tests/test_pg_fts.py
  2 个 adapter 测试
```

## 2. 查询

```sql
SELECT ... pdb.score(p.para_id) AS rank
FROM paragraphs p
WHERE p.text @@@ %s
ORDER BY rank DESC
LIMIT %s
```

关键词：

```text
any -> OR
all -> AND
```

## 3. 实际调用

```text
ParadeDBParagraphFTS.search(...)
n=10
cold 3.0s
warm ~0.1s
```

## 4. 开关

```text
SCIPAL_FTS_BACKEND=sqlite     默认
SCIPAL_FTS_BACKEND=paradedb   BM25
SCIPAL_FTS_BACKEND=postgres   native PG（已否决）
```

DSN：

```text
SCIPAL_PARADEDB_DSN
```

## 5. 当前范围

```text
已完成：paragraphs / summaries / sentences
未切换生产
```

## 6. 测试

```text
tests.test_pg_fts 8 OK
全量 851 tests OK
```

## 7. 下一步

```text
G1.2 PGSummaryBM25 ✅
G1.3 PGSentenceBM25 ✅
G1.4 查询语法（AND/短语）
G1.5 20/96 影子
```
