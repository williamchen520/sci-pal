# 外部评测：SciFact 适配器

> 目的：用 SciFact 摘要级 claim 验证，替代 auto 题做外部 smoke test。  
> 结论：数据可用；当前是独立 FTS 评测，不是 SciPal 完整检索链路。

## 1. 数据

- 官方 SciFact 数据（约 3.1 MB）；
- `corpus.jsonl`：5,183 篇摘要；
- `claims_train.jsonl`：claim + evidence sentence + SUPPORT/CONTRADICT；
- 已建独立库：`data/benchmark_scifact.db`（不提交）。

## 2. 构建

```powershell
python -m eval.scifact_benchmark --build
```

产物：

```
papers     = 5,183
sentences  = 45,051
claims     = 505（有 evidence 的 train claims）
```

## 3. 指标

- `doc_recall@10`：gold 文档是否进 top10；
- `sentence_recall@10`：gold evidence 句是否进 top100 句；
- `mrr`：第一个 gold 文档的倒数排名。

## 4. 结果

### 20 claims

| 指标 | 值 |
|---|---|
| doc_recall@10 | 1.00 |
| sentence_recall@10 | 0.85 |
| MRR | 0.645 |

### 100 claims

| 指标 | 值 |
|---|---|
| doc_recall@10 | **0.84** |
| sentence_recall@10 | **0.74** |
| MRR | **0.615** |

## 5. 解释

- 100 claims 更可信；
- 摘要级检索可以找到大部分 gold 文档；
- evidence 句 recall 0.74，说明“文档命中”不等于“证据句命中”；
- 当前只用了 FTS + BM25，没有用 SciPal 的向量/rerank/contextual，所以这是下限。

## 6. 局限

- 任务是 claim 验证，不是开放式 QA；
- 没有接入 SciPal 的 Flask/Chroma 链路；
- 没有评估答案生成、拒答、引用支持；
- 不能与内部 100 题直接比较。

## 7. 下一步

1. 把 SciFact 摘要导入 SciPal-compatible benchmark 库；
2. 接现有 retriever（向量 + FTS + rerank）；
3. 加 citation support / refusal 指标；
4. LitQA2 待论文导入方案确定后再做。

## 8. 复现

```powershell
python -m eval.scifact_benchmark --build --limit 100
```
