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

## 5. 配置对比（同 10 题）

| 配置 | coverage | avg citations | 单题耗时 |
|---|---|---|---|
| baseline | 0.4667 | 9.2 | 30–51s |
| adaptive contextual | **0.5000** | 10.1 | 20–51s |
| +sentence seeds | 0.3833 | 12.0 | 30–60s |

逐题 coverage：

| id | baseline | adaptive | seeds |
|---|---|---|---|
| q001 | 1.0 | 1.0 | 1.0 |
| q002 | 1.0 | 1.0 | 1.0 |
| q003 | 0.0 | 0.0 | 0.0 |
| q004 | 0.0 | 0.0 | 0.0 |
| q005 | 0.0 | 0.6667 | 0.0 |
| q006 | 0.5 | 0.5 | 0.5 |
| q007 | 0.0 | 0.5 | 0.0 |
| q008 | 1.0 | 1.0 | 1.0 |
| q009 | 0.6667 | 0.3333 | 0.3333 |
| q010 | 0.5 | 0.0 | 0.0 |

结论：

- adaptive contextual 的 answer coverage 最好；
- sentence seeds 虽然提高检索 Recall，但 answer coverage 反而下降；
- “检索到更多证据”不等于“回答覆盖更多 gold 点”，额外证据可能带来干扰；
- 10 题样本太小，且没有拒答样本，结论只作方向判断。

## 6. 30 题对比

| 配置 | coverage | avg citations | refusal_accuracy |
|---|---|---|---|
| 本地 7B baseline | 0.5444 | 10.77 | 0.25 |
| 本地 7B adaptive | 0.5722 | 14.17 | 0.25 |
| 云端 deepseek-chat | **0.9667** | **25.13** | **1.00** |

云端配置：

```
SCIPAL_LLM_PROVIDER=openai
SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
SCIPAL_LLM_MODEL=deepseek-chat
```

结论：

- 云端模型把 coverage 从 0.57 提到 0.97；
- refusal 从 0.25 提到 1.00；
- 引用数从 14 提到 25；
- 本地 7B 的 answer-level 结论不能代表产品。

> 指标修正：拒答现在允许“带引用的拒答陈述”（如 "does not contain"），不再要求引用数为 0。

### 100 题云端结果

| 指标 | 值 |
|---|---|
| answered | 100 |
| coverage | 0.7733 |
| avg citations | 27.11 |
| refusal_accuracy | 1.00 |

分题型 coverage：

| 类型 | coverage | n |
|---|---|---|
| factual | 1.0000 | 11 |
| methods | 1.0000 | 4 |
| comparison | 1.0000 | 5 |
| refusal | 1.0000 | 4 |
| multi_hop | 0.9167 | 4 |
| qualifier | 0.7778 | 3 |
| auto | **0.6860** | 69 |

结论：

- 人工 factual/methods/comparison 基本满分；
- auto 生成题拉低整体（0.686）；
- 30 题（0.9667）明显偏乐观，100 题更可信。

## 6.1 把 lenient 思路迁移到主 QA

尝试把 SciFact 的 lenient 判定迁移到 QA 拒答 prompt：

```
证据只覆盖部分问题时回答已支持部分；
只有完全没有证据才拒答。
```

30 题结果：

| 指标 | strict prompt | lenient prompt |
|---|---|---|
| coverage | 0.9667 | 0.9556 |
| avg citations | 25.13 | 24.00 |
| refusal_accuracy | **1.00** | **0.50** |

结论：

- coverage 略降；
- 拒答从 1.00 掉到 0.50；
- lenient 不适合 QA 拒答，已回退 strict；
- SciFact 的 lenient 只适用于 claim 判定，不适用于“证据不足要拒答”的 QA。

## 7. 30 题对比（旧）

| 配置 | coverage | avg citations | refusal_accuracy |
|---|---|---|---|
| baseline | 0.5444 | 10.77 | **0.00（0/4）** |
| adaptive contextual | **0.5722** | 14.17 | **0.00（0/4）** |

结论：

- adaptive 的 coverage 仍更高：+2.78pp；
- 引用数从 10.77 升到 14.17；
- 两个配置的 **answer-level refusal 都是 0**。

## 7. 关键发现：回答层不会拒答

检索层的 refusal：

```
0.75
```

回答层：

```
0/4
```

说明：

- 检索层能判断“证据不足”；
- 但 QA prompt / 模型仍然强行作答；
- 这会直接伤害可信度，比 Recall 的小幅提升更重要。

## 8. 下一步

1. 用同一批题比较 baseline / contextual / seeds 的 answer coverage；
2. 统计“检索到了 gold 但回答没覆盖”的比例；
3. 若 coverage 低主要来自回答组织，而不是检索，则优先改 prompt/证据选择，而不是继续改检索。
