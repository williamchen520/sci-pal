# P2：重建库 gold 与 before 基准

> 日期：2026-11-11  
> 状态：**gold 完成；向量基线完成；hybrid 基线受阻**

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

命令口径：

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

这是**段落级**指标，不是最终句级指标。

## 3. SciFact 300

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

## 4. 阻塞：hybrid before 基线

`scipal_rebuild` 没有 ParadeDB `pdb` schema：

```text
ParadeDB FTS failed: schema "pdb" does not exist
```

生产 `SCIPAL_PARADEDB_DSN` 指向：

```text
paradedb:5432/scipal_g0
```

不是 `scipal_rebuild`。

所以当前只能给：

```text
vector-only paragraph baseline
```

不能声称：

```text
hybrid before baseline
```

## 5. 下一步

```text
1. 在重建库安装/指向 ParadeDB BM25
2. 用同一 20 题跑 hybrid before
3. 句级证据命中口径
4. 再进 P3 滑窗
```

在 hybrid 基线完成前，P4 架构对照只能拿 vector 指标，不能拿最终指标。
