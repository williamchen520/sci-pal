# 实验记录：R11 双人 Reviewer 与 Kappa

> 日期：2026-11-13  
> 状态：**agreement/kappa API + UI 摘要通过**  
> 目标：双人独立裁决，机器只统计一致性

---

## 1. 规则

```text
每个 reviewer 独立提交
不覆盖别人的裁决
同一 rag 组取每个 reviewer 的最新裁决
计算 pairwise agreement + Cohen's kappa
```

## 2. API

```text
GET /api/rag/multi/<multi_run_id>/agreement
```

返回：

```text
reviewer_count
reviewers
pairwise[]
  reviewer_a
  reviewer_b
  items
  agreement
  kappa
disagreements[]
sufficient
```

## 3. Live

创建两个临时 reviewer，对同一 `code` 组分别：

```text
review_a accept
review_b reject
```

agreement：

```text
reviewer_count 3
pairwise:
  owner vs review_a  kappa 1.0
  owner vs review_b  kappa 0.0
  review_a vs review_b kappa 0.0
disagreements 2
```

临时 reviewer 和裁决已清理。

## 4. UI

evidence 页面显示：

```text
reviewers N
kappa X
disagreements N
```

只有一个 reviewer 时不显示 kappa。

## 5. 测试

```text
perfect agreement 1.0
known disagreement < 0.1
single rater not sufficient
```

```text
tests.test_rag_agreement 3 passed
validate_arch 243/243 OK
```

## 6. 边界

```text
没有 reviewer 指派
没有双人绑定到同一任务
样本 1 条时 kappa 不稳定
没有签名
```

kappa 只是统计，不是裁决。

## 7. 下一步

```text
reviewer 指派
双人任务完成度
签名/时间戳
```
