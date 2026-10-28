# 评测（eval/）

## 目录

```
eval/
├─ gold/seed.jsonl           # 30 题金标准
├─ results/                  # 运行结果（JSON）
├─ retrieval_eval.py         # Recall@k / MRR / nDCG / 拒答
└─ answer_eval.py            # 要点覆盖 / 禁用断言 / 引用数 / 拒答
```

## 金标准格式

```json
{
  "id": "q001",
  "question": "What is ICI rechallenge in HCC?",
  "paper_ids": ["paper_..."],
  "evidence": ["para_..._sent_001"],
  "answer_points": ["rechallenge after discontinuation"],
  "category": "factual",
  "difficulty": "easy",
  "forbidden": []
}
```

- `evidence`：可接受的证据句 ID（检索命中即可）；
- `answer_points`：答案中应覆盖的要点；
- `forbidden`：不允许出现的断言；
- 空 `evidence` 表示拒答题。

## 运行检索评测

```powershell
# 需要 Flask :5000
python eval/retrieval_eval.py --limit 10
python eval/retrieval_eval.py --limit 30 --output eval/results/retrieval_full.json
```

指标：

- `recall@k`：命中证据句 / 全部证据句；
- `mrr`：第一个命中位置的倒数；
- `ndcg@k`：二值相关性；
- `refusal_accuracy`：拒答题是否返回空证据。

## 运行答案评测

```powershell
python eval/answer_eval.py --answers eval/answers/sample.jsonl
```

答案文件：

```json
{"id": "q001", "answer": "Rechallenge is ... [P1]", "evidence_ids": ["P1"]}
```

指标：

- `coverage`：answer_points 覆盖率（token 重合 ≥50%）；
- `forbidden_hits`：禁用断言命中数；
- `avg_citations`：平均引用数；
- `refusal_accuracy`：拒答题是否无引用且包含拒答措辞。

## 基线

见 `eval/results/`。首次 5 题子集结果：

```json
{"questions": 5, "recall@10": 0.6, "mrr": 0.35, "ndcg@10": 0.4123}
```

## 回归门禁（待接 CI）

- PR 跑 20 题子集；
- `recall@10` 或 `ndcg@10` 下降 >2% 时失败；
- 结果写入 `eval/results/ci.json` 并作为 artifact。
