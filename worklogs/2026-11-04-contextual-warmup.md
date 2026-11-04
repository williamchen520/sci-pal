# Worklog: contextual warm-up

> 日期：2026-11-04  
> PR：Pending Review

## 1. 问题

首次请求仍 ~90–113s，虽然已开启 warmup。

## 2. 根因

生产：

```text
SCIPAL_CONTEXTUAL_MODE=always
真实请求使用 paragraphs_contextual
```

但 warmup 调的是默认 paragraphs collection，命中的是另一套索引。

## 3. 修复

```text
api_server.py
  warmup 时判断 contextual_mode=always
  vector_search(..., collection=contextual_collection)
  reranker 也预热

docker-compose.yml
  healthcheck start_period 180s -> 300s
```

## 4. 效果

```text
启动时间   约 4 分钟
首次请求   6.0s
热态请求   2.5s
```

GPU rerank：

```text
RTX 4060
full 20 candidates + 4000 chars
```

## 5. 质量（20 题，GPU）

```text
recall .650
MRR    .429
nDCG   .464
```

## 6. 当前生产

```text
SCIPAL_WARMUP=1
SCIPAL_RERANK=1
SCIPAL_RERANK_DEVICE=cuda
SCIPAL_FTS_BACKEND=sqlite
SCIPAL_MAX_QUERY_VARIANTS=2
app healthy
```

## 7. 测试

```text
全量 849 tests OK
```

## 8. 未完成项

```text
PR Pending Review
冷启动仍 4 分钟
```
