# 零技术债 Phase 5b：句子级原型对比

> 日期：2026-11-09  
> 状态：**对比脚本，不接生产路由**

---

## 1. 对比对象

### legacy

```text
旧 HybridSearch
段落向量 + 段落 BM25
RRF + 最终 cross-encoder
```

单查询实测：

```text
91.9s / 81.0s / 121.6s
平均 98.2s
```

完整 20 题旧基线：

```text
Recall@10 = 0.675
```

### sentence_hybrid 原型

```text
段落向量 top 30
句子 GIN top 100
句子得分 = 0.65 * 词法 + 0.35 * 父段落向量 prior
命中句子 top 100 进 rerank
扩展句不参与排序
```

---

## 2. 结果

```text
20 题
Recall@10        0.65
候选 Recall      0.85
平均耗时         13.0s
```

旧基线：

```text
Recall@10        0.675
平均耗时         98.2s
```

## 3. 结论

```text
速度：13s vs 98s，约 7.5 倍
召回：0.65 vs 0.675，低 2.5pp
```

候选里有 17/20 正确句子，最终只进 13/20，说明瓶颈在**句子级排序**，不是候选生成。

## 4. 未达生产原因

```text
1. 句子单独送 cross-encoder，缺少父段落语义
2. 100 条短句 rerank 仍比理想慢
3. 句子词法分和段落 prior 的权重尚未调
```

## 5. 下一步

```text
- 调 0.65/0.35 权重
- rerank 输入加父段落摘要/标题，但扩展句仍不单独参与打分
- 对比 20 题 Recall 是否回到 0.675
```

## 6. 文件

```text
scripts/compare_sentence_design.py
eval/results/sentence_hybrid_pool100_20.json
```
