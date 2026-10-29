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

## 4.1 接入 SciPal 检索核心

新增 `eval/scifact_scipal_eval.py`：

- 摘要摘要文档建 `papers/sections/paragraphs/sentences`；
- 建独立 `paragraphs` Chroma；
- 复用 `HybridSearch.vector_search` + `fts_search`；
- RRF 融合后取 top10；
- 不启用 ContextExpander / contextual / tree（避免生产依赖）。

100 claims：

| 检索方式 | doc_recall@10 | sentence_recall@10 | MRR |
|---|---|---|---|
| FTS-only | 0.84 | 0.74 | 0.615 |
| **向量 + FTS + RRF** | **0.97** | **0.97** | **0.828** |
| 再加 cross-encoder rerank | 0.97 | 0.96 | 0.828 |

结论：

- rerank 在摘要级 claim 上没有增益，甚至 sentence recall 略降；
- 默认保留“向量 + FTS + RRF”，`--rerank` 可选。

> ContextExpander 需要段落/章节窗口，SciFact 是“一篇摘要一个段落”的扁平结构；
> 直接接入返回空上下文，因此本适配器不启用 context expansion。

结论：

- 摘要级外部数据上，完整检索核心明显优于 FTS-only；
- 说明向量 + 融合 + rerank 的价值不依赖内部 HCC 语料；
- 仍未接入 context expansion / adaptive contextual。

构建命令：

```powershell
python -m eval.scifact_scipal_eval --build-db --build-index --limit 100
```

## 4.2 RRF 权重扫描

100 claims，向量/FTS 权重：

| 向量权重 | FTS 权重 | doc_recall@10 | sentence_recall@10 | MRR |
|---|---|---|---|---|
| 1.0 | 1.0 | 0.97 | 0.97 | 0.8276 |
| **1.2** | **0.8** | **0.97** | **0.97** | **0.8332** |
| 1.5 | 0.5 | 0.97 | 0.97 | 0.8318 |
| 0.8 | 1.2 | 0.90 | 0.90 | 0.7835 |
| 0.5 | 1.5 | 0.90 | 0.90 | 0.7743 |

结论：

- 向量权重过低（≤0.8）明显掉点；
- 1.2 / 0.8 的 MRR 最好，但 recall 不变；
- 收益太小，不修改生产默认权重。

## 4.3 Claim 验证（检索 + LLM）

新增 `eval/scifact_verification.py`：

```
claim → 向量+FTS 检索 top5 → 云端 LLM 判定 SUPPORT / CONTRADICT
```

50 claims：

| 指标 | 值 |
|---|---|
| accuracy | **0.74** |
| SUPPORT | 34 |
| CONTRADICT | 16 |

### 50 / 100 对比

| claims | accuracy | SUPPORT 正确率 | CONTRADICT 正确率 |
|---|---|---|---|
| 50 | 0.74 | — | — |
| 100 | **0.67** | **0.515** | **1.00** |

100 题混淆矩阵：

| gold \ pred | SUPPORT | CONTRADICT |
|---|---|---|
| SUPPORT | 35 | 33 |
| CONTRADICT | 0 | 32 |

说明：

- 模型几乎不会误判 CONTRADICT；
- 但 SUPPORT 有一半被保守判成 CONTRADICT；
- 结果偏向“证据不足就否定”，需要校准；
- 这不是完整 SciPal QA，且只到 100 题。

### Oracle 与 top-k 对比

| 证据 | accuracy | SUPPORT 正确率 | CONTRADICT 正确率 |
|---|---|---|---|
| 检索 top5 | 0.67 | 0.515 | 1.00 |
| 检索 top10 | 0.60 | — | — |
| **gold evidence** | **0.84** | **0.779** | **0.969** |

结论：

- 用 gold evidence 时 accuracy 从 0.67 提升到 0.84；
- 主要损失在 **证据选择**，不是模型推理；
- top10 反而降到 0.60，更多上下文带来噪声；
- 下一步应改 evidence selection / rerank，而不是加 top-k。

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
