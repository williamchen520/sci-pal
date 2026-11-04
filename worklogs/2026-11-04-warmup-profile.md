# Worklog: warm-up 与 rerank profile

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

按 profile 顺序，先降 query variants，再处理冷启动，最后看 rerank。

## 2. 改动

```text
services/search/hybrid_search.py
  SCIPAL_MULTI_QUERY
  SCIPAL_MAX_QUERY_VARIANTS 1..4

api_server.py
  SCIPAL_WARMUP=1 时启动预热 vector_search

deploy/.env.example
  对应开关
```

## 3. 实测

```text
cold / 2 variants    91.3s
warm / 2 variants     2.6s
warm / 4 variants     7.8s
rerank=True          >5 分钟未完成
```

启动 warm-up：

```text
启动 4–5 分钟
只预热向量，不解决 rerank
```

## 4. 结论

```text
rerank 是在线最大瓶颈
query variants 只影响热态 2.6 vs 7.8
cold start 约 90s
```

## 5. 当前生产

```text
SCIPAL_FTS_BACKEND=sqlite
SCIPAL_MAX_QUERY_VARIANTS=2
SCIPAL_WARMUP=0
app healthy
```

## 6. 测试

```text
tests.test_hybrid_env 2 OK
全量 846 tests OK
```

## 7. 未完成项

```text
PR Pending Review
rerank 候选/模型优化
```

## 8. 建议

```text
先把 rerank 候选从 40 降到 10–20
或按 category 关闭 rerank
再 profile 一次
```
