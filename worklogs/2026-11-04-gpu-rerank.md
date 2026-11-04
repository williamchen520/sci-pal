# Worklog: GPU rerank

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

CPU rerank 不可用；优先尝试 GPU。

## 2. 环境

```text
NVIDIA GeForce RTX 4060 8GB
Docker nvidia runtime 可用
容器内 torch.cuda.is_available() = True
```

## 3. 改动

```text
services/search/reranker.py
  SCIPAL_RERANK_DEVICE=cuda
  未设置时自动 cuda/cpu

deploy/docker-compose.yml
  app: gpus: all

生产 env：
  SCIPAL_RERANK=1
  SCIPAL_RERANK_K_MULT=4
  SCIPAL_RERANK_MAX_ITEMS=40
  SCIPAL_RERANK_MAX_CHARS=4000
  SCIPAL_RERANK_DEVICE=cuda
```

## 4. 效果

```text
冷启动 + rerank   113.4s
warm rerank         2.7s
```

对比 CPU：

```text
20.6s（截断）
>5min（完整）
```

## 5. 质量（20 题）

```text
recall@10   0.650
MRR         0.429
nDCG@10     0.464
```

对比基线：

```text
recall .650
MRR    .425
nDCG   .461
```

质量保持，延迟达标。

## 6. 测试

```text
全量 849 tests OK
```

## 7. 风险

```text
首次请求仍冷启动 ~113s
GPU 与宿主共享 8GB
需监控显存
```

## 8. 未完成项

```text
PR Pending Review
启动 warmup 是否开启
```
