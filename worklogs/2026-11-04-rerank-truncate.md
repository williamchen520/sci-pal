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

## 5. 质量

```text
未复跑 20/96 recall
截断可能影响长段落排序
```

## 6. 测试

```text
tests.test_reranker 1 OK
全量 847 tests OK
```

## 7. 未完成项

```text
PR Pending Review
rerank 质量评估
进一步降低 rerank 候选
```
