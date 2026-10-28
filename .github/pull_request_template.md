## 1. 背景描述

<!-- 为什么要做这个改动？解决什么问题？关联 issue/讨论。 -->

## 2. 核心改动

<!-- 改了什么：模块、接口、行为、兼容性。 -->

## 3. 基准测试指标变化

<!--
必须填写。评测语料：本地论文库（当前 3,297 篇；若用 500 篇子集请注明）。
评测集：eval/gold/seed_100.jsonl（100 题，30 curated + 70 auto）。
命令：python eval/retrieval_eval.py --limit 30
输出：eval/results/xxx.json
-->

| 指标 | 基线 | 变更后 | 变化 |
|---|---|---|---|
| Recall@10 |  |  |  |
| MRR |  |  |  |
| nDCG@10 |  |  |  |
| refusal_accuracy |  |  |  |

### 测试

<!-- python -m unittest discover -s tests -p "test_*.py" 结果；新增测试数量。 -->
