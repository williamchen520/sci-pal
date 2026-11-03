# Worklog: PG FTS 候选召回实验

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

v2 显示 PG match recall 高但排序慢；尝试“先召回 200 候选，再排序/重排”。

## 2. 改动

```text
services/search/pg_fts.py
  PGParagraphFTS.recall
  PGSummaryFTS.recall
  无 ORDER BY，LIMIT top_n

tests/test_pg_fts.py
  recall 无 ORDER BY 测试
```

## 3. 结果

20 query，top_n=200：

```text
paragraph recall 0.08  avg 0.31s  max 1.74s
summary   recall 0.31  avg 0.26s  max 2.69s
```

结论：

```text
无排序 LIMIT 不是“召回 top 200”
只是任意 200 行
SQLite top-10 大部分不在其中
不能用于候选召回
```

## 4. 性能根因

`EXPLAIN ANALYZE`：

```text
Parallel Seq Scan on paragraphs
Filter: search_vector @@ tsquery
Rows Removed by Filter: 32,432
```

宽泛 OR term 命中约 55% 行，规划器放弃 GIN，改全表扫描。

```text
q002 6 terms: ~9.2s
```

## 5. 当前结论

```text
PG FTS 召回可行（v2 match recall 0.975/1.0）
排序慢
无排序候选召回不可用
需要 term frequency / rare-term 选择
```

## 6. 测试

```text
tests.test_pg_fts 5 OK
全量 836 tests OK
```

## 7. 未完成项

```text
PR Pending Review
term frequency 选词
ranked candidate recall
```
