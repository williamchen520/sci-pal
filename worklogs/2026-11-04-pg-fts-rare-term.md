# Worklog: PG FTS rare-term 选词 v4

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

宽泛 OR term 命中 55% 行，PG 走 seq scan；需要 rare-term 选词。

## 2. 改动

```text
scripts/build_pg_term_stats.py
  fts_term_stats(source, word, ndoc, nentry)
  paragraphs 394,025 terms
  summaries   84,059 terms
  sentences  393,781 terms

services/search/pg_fts.py
  to_tsvector -> lexeme
  按 nentry 升序选 rare terms
  term_limit=4
```

## 3. v4 结果（20 query，top-10）

```text
paragraph Jaccard      0.200
paragraph match recall 0.975
summary Jaccard        0.411
summary match recall   0.985
```

对比：

| 版本 | paragraph Jaccard | match recall | summary Jaccard | match recall |
|---|---:|---:|---:|---:|
| v2 term6 | 0.109 | 0.975 | 0.313 | 1.000 |
| v3 term3 | 0.184 | 0.855 | 0.294 | 0.810 |
| **v4 term4 rare** | **0.200** | **0.975** | **0.411** | **0.985** |

## 4. 延迟

```text
q001 2.46s
q002 3.37s
q003 5.15s
```

仍高于 SQLite 0.1–0.2s。

## 5. 测试

```text
tests.test_pg_fts 6 OK
全量 837 tests OK
```

## 6. 风险 / 外部 API

```text
无生产路由变化
fts_term_stats 需定期重建
rank 仍未对齐
```

## 7. 未完成项

```text
PR Pending Review
rerank / ranking 对齐
延迟优化
```
