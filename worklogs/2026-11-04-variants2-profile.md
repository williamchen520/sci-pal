# Worklog: query variants 2 + profile

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

按 profile 建议先把 query variants 从 4 降到 2，观察完整请求耗时。

## 2. 改动

```text
services/search/hybrid_search.py
  SCIPAL_MULTI_QUERY=0/1
  SCIPAL_MAX_QUERY_VARIANTS=1..4

deploy/.env.example
  SCIPAL_MULTI_QUERY=1
  SCIPAL_MAX_QUERY_VARIANTS=4

生产临时：
  SCIPAL_MAX_QUERY_VARIANTS=2
```

## 3. 冷/热对比

`UnifiedRetriever(rerank=False)`：

```text
第一次   91.3s   (模型/Chroma 冷启动)
第二次    2.6s   (2 variants)
```

4 variants：

```text
第一次  121.9s
第二次    7.8s
```

## 4. rerank=True

尝试 profile：

```text
30+ 分钟未完成
CPU 99%
```

说明：

```text
rerank 是端到端最大瓶颈
不是 query variants
```

## 5. 结论

```text
冷启动 ~90s
warm 2 variants 2.6s
warm 4 variants 7.8s
rerank=True 仍不可在线
```

## 6. 测试

```text
tests.test_hybrid_env 2 OK
全量 846 tests OK
```

## 7. 未完成项

```text
PR Pending Review
启动 warm-up
rerank 候选/模型优化
```

## 8. 当前生产

```text
SCIPAL_FTS_BACKEND=sqlite
SCIPAL_MAX_QUERY_VARIANTS=2
app healthy
```
