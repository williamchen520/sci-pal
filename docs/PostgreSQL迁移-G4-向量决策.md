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


## 7. G4a 进度

```text
deploy/sql/006_paragraph_embeddings.sql
scipal_bench.paragraph_embeddings
```

回填：

```text
166,470 / 166,470
```

HNSW：

```text
CREATE INDEX 因 /dev/shm 不足失败
```

当前索引：

```text
pkey
paper_idx
无 HNSW
```

pgvector 连接：

```text
改为 SCIPAL_PG_DSN 优先
```

生产：

```text
Chroma 保持
```

## 8. 下一步

```text
G4a1 调整 shared memory 或 maintenance_work_mem
G4a2 建 HNSW
G4b  pgvector 同口径复测
```


## 9. G4b1 语料审计

```text
chroma_total        166470
pg_total            167388
missing_in_pg       0
extra_in_pg         918
orphan_embeddings   0
paragraphs_no_emb   918
paper_id_mismatch   0
text_checked        5000
text_mismatch       124
paper_count_diff    101
```

结论：

```text
Chroma 索引的是旧 SQLite 语料
PG 有 918 段未被 Chroma 索引
5000 段抽样中 124 段正文不一致
```

样例：

```text
paper_PMC11649735_c5072470_xml_para_00004
chroma 199 chars
pg     1273 chars
```

文本差异不是单纯空白，是解析/清洗版本漂移。

因此：

```text
Chroma .75 是旧语料上的分数
不能直接作为 pgvector 的公平基准
```

下一步：

```text
G4b2 用 PG 快照重建干净 Chroma
G4b3 同一语料上比较 Chroma / pgvector
G4b4 接入公开 qrels
```
