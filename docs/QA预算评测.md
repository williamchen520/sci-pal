# QA 预算评测（简单/复杂 × top10/top20）

> 脚本：`eval/qa_budget_eval.py`
> 结果：`eval/results/qa_budget_100.json`
> 说明：评测检索层（evidence + sufficient），不调用 LLM。

## 1. 分层规则

`services/qa/budget.py`：

- 简单：默认 top10；
- 复杂：长度 ≥120、多个问号、或含 review/comparison/综述/比较/all studies 等 → top20。

## 2. 100 题结果

| 分层 | 问题数 | 预算 | Recall@k | paragraph_sentence_recall | refusal |
|---|---|---|---|---|---|
| simple | 50 | 10 | 0.4200 | 0.6600 | **0.75** |
| simple | 50 | 20 | **0.5300** | **0.7400** | 0.50 |
| complex | 46 | 10 | 0.6630 | 0.8478 | — |
| complex | 46 | 20 | **0.7283** | **0.8696** | — |

## 3. 30 题结果

| 分层 | 问题数 | 预算 | Recall@k | refusal |
|---|---|---|---|---|
| simple | 23 | 10 | 0.4783 | **0.75** |
| simple | 23 | 20 | 0.6304 | 0.50 |
| complex | 3 | 10 | 0.8333 | — |
| complex | 3 | 20 | 0.8333 | — |

30 题 complex 样本太少，100 题更可靠。

## 4. 结论

- 扩大预算对两层的 Recall 都有提升：
  - simple：+0.11（100 题）
  - complex：+0.065（100 题）
- 但 simple 层的拒答准确率从 **0.75 → 0.50**；
- complex 层当前没有拒答题，扩大预算没有拒答代价。

## 5. 推荐策略

```
简单问题：top10（保拒答）
复杂问题：top20（提召回）
```

即当前 `SCIPAL_QA_ADAPTIVE_TOPK` 默认行为。

如果某类复杂问题开始出现误答，可以再把复杂层降到 15 或按题型细分。

## 6. 复现

```powershell
python -m eval.qa_budget_eval `
  --gold eval/gold/seed_100.jsonl `
  --limit 100 `
  --output eval/results/qa_budget_100.json
```
