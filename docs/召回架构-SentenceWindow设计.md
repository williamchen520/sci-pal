# 召回架构原型：Sentence Window Hybrid

> 日期：2026-11-10  
> 状态：**eval 原型，不接生产路由**

---

## 1. 目标

```text
找对句子
+ 还原段落原意
```

原则：

```text
排序单元 = 句子
语义单元 = 段落
上下文单元 = 句子窗口 / 父段落
扩展句不参与任何排序
```

---

## 2. 设计

```text
段落向量 top 30
  -> 只作为句子的 paragraph prior

句子 GIN top 100
  -> 句子词法命中

候选 =
  词法 top 100
  ∪ top 30 段落内所有句子

score =
  0.7 * RRF(句子词法 rank)
  + 0.3 * RRF(段落向量 rank)
```

精排：

```text
top 20 候选句子
  -> cross-encoder
  -> top 10 anchors
```

上下文：

```text
anchor sentence
  -> 父段落 <= 600 字符：整段
  -> 父段落 > 600 字符：±2 句窗口
```

窗口：

```text
只有 anchor 带分
窗口句子 context_scored=false
不进入 rerank / MMR
```

---

## 3. 模块

```text
services/search/sentence_window.py
  build_context()

services/search/sentence_hybrid.py
  SentenceHybridRetriever.search()

scripts/compare_sentence_window.py
  20/10 题 eval
```

---

## 4. 10 题结果

```text
Recall@10       0.80
平均耗时        39.75s
平均上下文字符  7198
```

漏题：

```text
q007  ctDNA precision medicine
q009  colorectal cancer global challenges
```

都是候选未覆盖，不是排序问题。

---

## 5. 结论

```text
设计有效：10 题 8 中
上下文可控：约 7.2k 字符
速度仍是瓶颈：CPU cross-encoder 约 1s/句
```

对比：

```text
旧引擎       0.675 / 98.2s
上一版原型   0.65  / 13.0s
本设计       0.80  / 39.8s（10 题）
```

本设计召回更高，但 rerank 成本更高；需要 GPU 或更小 rerank 池。

---

## 6. 下一步

```text
1. 20 题完整评估
2. rerank pool / max_chars 调参
3. q007/q009 候选覆盖
4. 与旧引擎同题对比
```
