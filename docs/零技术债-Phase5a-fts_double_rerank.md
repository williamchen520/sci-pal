# 零技术债 Phase 5a：移除 FTS 双重 rerank

> 日期：2026-11-09  
> 状态：**FTS 召回不再跑 cross-encoder**

---

## 1. 根因

`PGParagraphRetriever.search()` 在 FTS 候选召回后调用：

```text
Reranker.rerank(50 candidates)
```

`UnifiedRetriever` 随后又对 fused 结果：

```text
Reranker.rerank(40 candidates)
```

一次查询实际跑了约 140 对 cross-encoder，长文本 4000 字符，这是 2–6 分钟的主因。

## 2. 改动

```text
services/search/pg_paragraph_retriever.py
  删除内部 Reranker
  FTS 候选直接按 hit.rank 返回
  外层 UnifiedRetriever 保留最终 rerank
```

## 3. 测试

```text
test_pg_paragraph_retriever   2 passed
```

测试改为断言 FTS rank 映射，不再依赖 fake reranker。

## 4. 预期

```text
FTS 召回从 ~225s 降到百毫秒级
最终排序仍由外层 cross-encoder 决定
```

## 5. 验证

部署后：

```text
单查询时间
20 题回归
A/B
```
