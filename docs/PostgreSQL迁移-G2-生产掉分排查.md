# G2 生产掉分排查：5 个边界差异

> 日期：2026-11-04  
> 对象：pgvector 离线 .7604 vs 生产 .6250

## 1. ef_search

代码：

```python
pg.execute(f"SET hnsw.ef_search = {ef_search}")
```

结论：

```text
按查询设置，不是全局持久
连接池第一次取出的连接默认仍是 40
```

生产修复：

```sql
ALTER DATABASE scipal_g0 SET hnsw.ef_search = 200;
```

代码默认值：

```text
SCIPAL_PGVECTOR_EF_SEARCH=200
```

## 2. Reranker

生产环境：

```text
SCIPAL_RERANK=1
SCIPAL_RERANK_DEVICE=cuda
SCIPAL_RERANK_MAX_ITEMS=40
SCIPAL_RERANK_MAX_CHARS=4000
```

实测：

```text
nvidia-smi 显存 3.3GB
日志出现 “Hybrid recall: 50 candidates -> rerank top 40”
```

结论：

```text
GPU reranker 确实生效
没有静默跳过
```

## 3. 流水线顺序

`UnifiedRetriever`：

```text
1. vector + fts
2. rrf_fuse
3. entity boost
4. rerank
5. MMR
```

结论：

```text
Rerank 在 MMR 之前
```

但离线脚本：

```text
BM25 + vector -> RRF -> rerank
没有 MMR
```

这是真实差异。

## 4. RRF 权重

离线：

```text
单查询
vector + BM25
等权 1/(60+rank)
```

线上：

```text
SCIPAL_MULTI_QUERY=1
2 个 query variants
rrf_fuse_multi 等权
entity boost 追加候选
```

结论：

```text
线上不是单查询等权 RRF
多 query + entity boost 改变了候选池
```

`_compute_dynamic_weights` 只在单查询路径使用，多查询路径未使用。

## 5. 候选池

生产：

```text
candidate_k = max(top_k * 5, 50) = 50
rerank_k = top_k * 4 = 40
SCIPAL_RERANK_MAX_ITEMS = 40
```

结论：

```text
没有截断到 Top-5
不是候选池不足
```

## 6. 额外发现：entity boost 去重 bug

原代码：

```python
existing_ids = {p.get("paragraph_id") or p.get("id") for p in fused}
new_hits = [...]
```

实际 FTS 字段是 `para_id`，导致：

```text
existing_ids = {None}
所有 entity hits 被当成重复
entity boost 实际 +0
```

已修：

```text
统一用 para_id
去重后再追加
```

效果：

```text
20 题 recall .65 -> .75
96 题 .6875（持平）
```

说明：

```text
entity bug 是真的
但不是 96 题掉分的主因
```

## 7. 当前结论

```text
Reranker   正常
候选池     正常
EF         已持久化
Entity     已修
```

最可能的剩余主因：

```text
多 query variants + entity boost + MMR
使线上候选分布偏离离线单查询 RRF
```

## 8. 下一步 A/B

```text
A: SCIPAL_MULTI_QUERY=0
B: 关闭 entity boost
C: MMR=0
D: 三者组合
```

每组跑 20 题，找到最大差异项后再跑 96。

## 9. 当前生产

```text
FTS       ParadeDB 100%
Vector    Chroma
Reranker  GPU
app       healthy
```
