# G4 向量决策

日期：2026-11-06

## 1. 20 题基线

| 方案 | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| Chroma | 0.7500 | 0.4392 | 0.4961 |
| BM25-only | 0.6250 | 0.4517 | 0.4649 |
| pgvector | 0.7000 | 0.4422 | 0.4747 |

## 2. BM25-only

真实关闭向量后：

```text
recall 0.625
nDCG   0.4649
```

明显低于 Chroma，不能去向量。

## 3. pgvector 根因

适配器使用：

```text
SCIPAL_PARADEDB_DSN
  -> paradedb:5432/scipal_g0
```

不是生产：

```text
SCIPAL_PG_DSN
  -> scipal_bench
```

生产 `scipal_bench` 没有 `paragraph_embeddings` 表：

```text
relation "paragraph_embeddings" does not exist
```

所以 pgvector 0.70 是影子库结果，不是生产候选。

## 4. 结论

```text
G4 阻塞
Chroma 继续生产
pgvector 不能直接切
```

## 5. 下一步

```text
G4a 在 scipal_bench 建 paragraph_embeddings
G4b 从 Chroma 回填
G4c 同口径复测 20 / 92
G4d 达标再切
```

## 6. 测试开关

新增：

```text
SCIPAL_VECTOR_ENABLED=0
```

仅用于 BM25-only 评估，默认开启。
