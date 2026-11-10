# P2：重建库 gold 与 before 基准

> 日期：2026-11-11  
> 状态：**gold 完成；paragraph 级 vector / hybrid 基线完成；句级与 rerank 未完成**

---

## 1. 内部 20 题

文件：

```text
eval/gold/rebuild_20.jsonl
```

来源：

```text
eval/gold/seed_100.jsonl
```

筛选：

```text
论文在 scipal_rebuild 存在
旧证据句可映射到重建句 ID
每题保留 answer_points
覆盖 11 篇论文
```

ID 映射：

```text
paper_PMC..._<hash>_xml_para_NNNNN_sent_MMM
  -> paper_PMC..._para_NNNNN_sent_MMM
```

验证：

```text
20/20 题 evidence 全部存在
```

## 2. 向量基线

口径：

```text
scipal_rebuild
pgvector HNSW
paragraph-only
no BM25
no rerank
```

结果：

```text
Recall@10 = 0.6000
MRR       = 0.3122
nDCG@10   = 0.3803
```

文件：

```text
eval/results/rebuild_20_vector_paragraph.json
```

## 3. Hybrid 基线

口径：

```text
pgvector HNSW top20
+ PostgreSQL native FTS top20
+ RRF k=60
+ top10 paragraphs
+ no rerank
```

结果：

```text
Recall@10 = 0.7000
MRR       = 0.4238
nDCG@10   = 0.4894
```

文件：

```text
eval/results/rebuild_20_hybrid_paragraph.json
```

相对 vector：

```text
Recall +0.10
MRR    +0.1116
nDCG   +0.1091
```

## 4. 为什么不用 ParadeDB

`scipal_rebuild` 没有 ParadeDB `pdb` schema：

```text
ParadeDB FTS failed: schema "pdb" does not exist
```

生产 `SCIPAL_PARADEDB_DSN` 指向：

```text
paradedb:5432/scipal_g0
```

不是重建库。

重建库已有：

```text
paragraphs.search_vector
paragraphs_search_idx (GIN)
```

所以本轮用 native FTS 做 before 对照，不冒充 ParadeDB。

## 5. 为什么是 paragraph 级

句级需要 `to_evidence_json` 的 highlight，但该路径有 sufficiency LLM 门控：

```text
20 题跑 40 分钟未完成
```

本轮直接对 `paragraph_embeddings` 和 `paragraphs.search_vector` 打分，避免 LLM 门控。

因此：

```text
这些数字是 paragraph recall
不是最终 sentence recall
```

## 6. SciFact 300

```text
queries = 300
docs    = 5183
```

结果：

```text
pg_recall@10    = 0.8669
pg_ndcg@10      = 0.7458
chroma_recall   = 0.8669
chroma_ndcg     = 0.7473
exact_recall    = 0.8669
exact_ndcg      = 0.7458
HNSW/exact 重叠 = 10.0
```

文件：

```text
eval/results/scifact_300_backends.json
```

结论：

```text
HNSW 与 exact 等价
pgvector 与 Chroma 基本等价
```

## 7. 结论与限制

已完成：

```text
内部 20 题 gold
vector paragraph baseline
native-FTS hybrid paragraph baseline
SciFact 300 vector baseline
```

未完成：

```text
sentence-level evidence recall
rerank on/off 对照
ParadeDB BM25 对照
```

P4 架构对照可以使用本轮 paragraph 基线；但不能把它当最终句级指标。
