# QA 答案级评测（异步）

> 目的：不再只看检索指标，直接评估最终回答的覆盖、引用与拒答。

## 1. 为什么用异步

本地 7B 单题生成约 20–50 秒，同步 `/api/qa/ask` 容易超时。  
改用：

```
POST /api/qa/ask_async
→ 轮询 /api/review/task/<id>
→ completed 后取 result
```

脚本：

```
python -m eval.qa_answer_async_eval --limit 10
```

## 2. 指标

- `coverage`：回答覆盖 gold answer points 的比例；
- `forbidden_hits`：是否出现禁止内容；
- `avg_citations`：平均引用数；
- `refusal_accuracy`：拒答题正确率；
- 单题耗时。

## 3. 首轮结果（10 题）

| 指标 | 值 |
|---|---|
| answered | 10 |
| coverage | 0.50 |
| forbidden_hits | 0 |
| avg_citations | 10.1 |
| 单题耗时 | 20.1–51.1s |

引用数分布：

```
q001 10, q002 3, q003 6, q004 7, q005 10
q006 8, q007 11, q008 10, q009 1, q010 3
```

## 4. 观察

- 回答长度 2.3k–4.6k 字符；
- 引用基本存在，但 q009 只有 1 条；
- coverage 0.50，说明“答得多”不等于“答到 gold 点”；
- 当前 10 题没有拒答样本，refusal_accuracy 不具意义。

## 5. 下一步

1. 用同一批题比较 baseline / contextual / seeds 的 answer coverage；
2. 统计“检索到了 gold 但回答没覆盖”的比例；
3. 若 coverage 低主要来自回答组织，而不是检索，则优先改 prompt/证据选择，而不是继续改检索。
