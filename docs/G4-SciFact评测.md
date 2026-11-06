# SciFact 外部评测：pgvector vs Chroma

> 日期：2026-11-07  
> 数据：SciFact（BEIR 版）  
> 查询：300 条 test qrels  
> 文档：5,183 篇摘要

---

## 1. 目的

用公开 qrels 回答一个问题：

```text
pgvector 与 Chroma 的差异
是 SciPal 内部标注偏差，还是通用检索差异
```

---

## 2. 设置

```text
corpus        5,183
queries         300
embedding     bge-base-en-v1.5
dimension      768
metric         cosine
top_k          10
```

三种检索：

```text
pgvector HNSW
pgvector 精确扫描
Chroma HNSW
```

HNSW：

```text
m=16
ef_construction=64
ef_search=200
```

---

## 3. 结果

| 方法 | Recall@10 | nDCG@10 |
|---|---:|---:|
| pgvector HNSW | 0.8669 | 0.7458 |
| pgvector 精确 | 0.8669 | 0.7458 |
| Chroma | 0.8636 | 0.7449 |

重合：

```text
pgvector HNSW vs 精确   10.00 / 10
pgvector vs Chroma       9.93 / 10
```

---

## 4. 结论

```text
在公开 SciFact 上
pgvector 略优于 Chroma
且 HNSW 与精确检索 top10 完全一致
```

这说明：

```text
前一轮 0.72 vs 0.75 的差异
主要是内部 20 题 gold 的偏差
不是 pgvector 通用能力不足
```

---

## 5. 局限

```text
SciFact 是摘要级
不是全文段落级
查询是 claim 验证，不是开放问答
```

因此它是外部效度证据，不是 SciPal 全量替代指标。

---

## 6. 建议

```text
保留 pgvector 为生产
Chroma 继续冷备
1 万篇阶段再跑一次全文评测
```

---

## 7. 复现

```text
python eval/scifact_backends.py
```

输出：

```text
eval/results/scifact_backends.json
```
