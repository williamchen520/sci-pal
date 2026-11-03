# Worklog: 接入 PG FTS term3 + rerank

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

按 A 方案接受 4s，把 PG term3 候选 + cross-encoder rerank 接入 HybridSearch。

## 2. 改动

```text
services/search/pg_paragraph_retriever.py
  PGParagraphFTS term_limit=3
  candidates=50
  Reranker top_k
  输出 HybridSearch 兼容 dict

services/search/hybrid_search.py
  SCIPAL_FTS_BACKEND=postgres 时走 PG
  PG 异常/空结果 fallback SQLite
  year/journal 过滤仍走 SQLite
  paper_ids 在 PG 结果上过滤

deploy/.env.example
  SCIPAL_FTS_BACKEND=sqlite
  SCIPAL_PG_FTS_CANDIDATES=50
  SCIPAL_PG_FTS_TERM_LIMIT=3
```

## 3. 行为

```text
默认 sqlite -> 不变
postgres -> PG 候选 + rerank
PG 失败 -> 自动 SQLite
```

## 4. 测试

```text
tests.test_pg_paragraph_retriever 2 OK
全量 843 tests OK
```

真实请求：

```text
q001 top1 = para_paper_PMC12707946_2d3bcc67_0008
score = 0.998
```

首次请求含模型加载，后续约 4s。

## 5. 风险

```text
首次请求慢（模型加载）
4s 延迟需接受
依赖 PG + reranker
```

## 6. 未完成项

```text
PR Pending Review
生产启用 SCIPAL_FTS_BACKEND=postgres
20/96 eval 复跑
```
