# Worklog: rerank 截断与候选上限

> 日期：2026-11-04  
> PR：Pending Review

## 1. 问题

rerank=True 在线不可用：

```text
10 candidates 也超过 4 分钟
CPU 99%
```

## 2. 根因

cross-encoder 输入是完整 paragraph，文本过长。

实测 10 条长文本：

```text
1 thread  56.5s
```

截断后：

```text
200 chars  9.9s
400 chars  6.9s
800 chars 13.9s
```

## 3. 改动

```text
services/search/reranker.py
  SCIPAL_RERANK_MAX_ITEMS=20
  SCIPAL_RERANK_MAX_CHARS=400

api_server.py
  SCIPAL_RERANK=1/0

生产：
  SCIPAL_RERANK=1
  SCIPAL_RERANK_K_MULT=2
```

## 4. 实测

```text
冷启动 + rerank  133.3s
warm rerank       20.6s
```

对比之前：

```text
>5 分钟未完成
```

改善明显，但仍未到 4s。

## 5. 质量复跑

20 题回归：

```text
rerank 关闭         recall .575 / MRR .229
截断 rerank 20      recall .425 / MRR .341
```

结论：

```text
截断 rerank 质量反而更差
不能接受
```

40 条截断版：

```text
8 分钟只跑 5 题
过慢，中止
```

## 6. 测试

```text
tests.test_reranker 1 OK
全量 847 tests OK
```

## 7. 最终处理

```text
生产 SCIPAL_RERANK=0
接口恢复 4.2–4.4s
rerank 只保留离线/实验用途
```

## 8. 未完成项

```text
PR Pending Review
小模型 / GPU / 专用 rerank
```
