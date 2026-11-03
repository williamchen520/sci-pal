# Worklog: PG FTS 候选 + rerank

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

PG rare-term 召回已可用，但 top-k 排序仍落后；尝试候选集 + cross-encoder 重排。

## 2. 改动

```text
scripts/fts_rerank_shadow.py
  SQLite top10 基线
  PG rare-term top50 候选
  Reranker top10
  nDCG / 延迟

tests/test_fts_rerank_shadow.py
  gold para 映射
  nDCG
```

## 3. 结果（20 query）

```text
SQLite nDCG        0.532
PG raw nDCG        0.343
PG + rerank nDCG   0.633
```

提升：

```text
+0.101 vs SQLite
+0.290 vs PG raw
```

延迟：

```text
PG 候选       3.14s
rerank        1.53s
合计          4.67s
```

## 4. 解读

```text
PG raw 排序差
cross-encoder 能纠正大部分排序
候选召回足够（v4 match recall 0.975）
```

## 5. 测试

```text
tests.test_fts_rerank_shadow + tests.test_pg_fts
8 tests OK
全量 839 tests OK
```

## 6. 风险 / 外部 API

```text
无生产路由变化
20 query 小样本
nDCG 为单一 gold
延迟 4.7s 仍高
```

## 7. 未完成项

```text
PR Pending Review
更大样本评估
延迟优化
生产候选/重排接入
```
