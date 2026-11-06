# G4 HNSW 诊断

日期：2026-11-06

## 1. 问题

pgvector 生产 20 题：

```text
Chroma   .7500 / .4961
pgvector .7250 / .4847
```

需要判断：是 HNSW 近似导致，还是查询/融合逻辑不同。

## 2. 单题 top10

同一 query embedding：

```text
Chroma top10 == pgvector top10
```

完全一致。

## 3. 20 题 top10 重合

```text
pgvector HNSW vs 精确扫描   199 / 200
Chroma       vs 精确扫描   192 / 200
Chroma       vs pgvector   191 / 200
```

结论：

```text
HNSW 近似本身影响很小（1/200）
Chroma 与 pgvector 的差异主要是两套 HNSW 图不同
```

## 4. 参数差异

Chroma collection：

```text
hnsw:M              16
hnsw:space          cosine
hnsw:construction_ef 100
```

pgvector 索引：

```text
m                16
ef_construction  64（默认）
ef_search        200
```

`ef_construction` 不同，邻居图不同，top10 会不同。

## 5. 查询逻辑差异

```text
Chroma:
  query embedding 未显式 normalize
  where 过滤在查询内
  n_results=top_k

pgvector:
  query embedding normalize=True
  paper 过滤在 ANN 之后
  LIMIT top_k
```

对于无过滤的 20 题，过滤顺序不影响；cosine 下 normalize 也不应改变排序。

因此不是融合算法差异；RRF 仍按 rank。

## 6. 重建尝试

尝试：

```sql
DROP INDEX paragraph_embeddings_hnsw;
CREATE INDEX ... WITH (m=16, ef_construction=100);
```

`DROP INDEX` 在生产连接下长时间等待，已终止，保留旧索引。

当前索引仍在，`reloptions` 为空（默认参数）。

## 7. 结论

```text
HNSW 没有改变检索算法
差异来自 ANN 图参数/实现
```

下一步：

```text
1. 维护窗口重建 m=16, ef_construction=100
2. 复测 top10 重合与 20 题
3. 若仍低，再调 RRF / 候选数
```

## 8. 当前生产

```text
Chroma 生产
pgvector 索引存在但未启用
app healthy
```
