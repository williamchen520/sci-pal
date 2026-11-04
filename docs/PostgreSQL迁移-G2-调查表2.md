# G2 调查表 2：Evidence 单位、Anchor 与上下文组装

> 日期：2026-11-04  
> 问题：召回、组装、评测、模型消费四层数据契约不一致  
> 目标：找到社区/论文可复用方案，形成 G2 补充计划

---

## 1. 调查结论

社区和论文的主流方案集中在四条：

```text
1. sentence-window / parent-document retrieval
2. contextual retrieval / late chunking
3. submodular evidence selection
4. stage-wise evaluation + lost-in-the-middle 处理
```

最直接对应我们问题的是：

```text
sentence-window / parent-document
submodular evidence selection
```

---

## 2. 方案对照

| 方案 | 代表来源 | 解决的问题 | 对我们的适用性 |
|---|---|---|---|
| Sentence Window / Parent Document | LangChain `ParentDocumentRetriever`、LlamaIndex sentence window | 小单元召回，大上下文交付 | **最适用** |
| Contextual Retrieval | Anthropic Contextual Retrieval | chunk 前置上下文，提升召回 | 适用，主要修召回 |
| Late Chunking | Late Chunking 论文 | 长上下文 embedding，减少 chunk 语义丢失 | 适用，偏索引层 |
| Submodular Evidence Selection | TREC RAG 2025、submodular evidence packing | 预算内选非冗余证据 | **最适用** |
| Stage-wise Evaluation | CLEAR-RAG | 分开评估 retrieval/context/generation | 直接适用 |
| Lost-in-the-middle 处理 | 长上下文研究 | 关键证据位置/顺序 | 适用 |

---

## 3. Sentence Window / Parent Document

来源：

- [LangChain ParentDocumentRetriever](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/)
- [LlamaIndex sentence window 思路](https://developer.aliyun.com/article/1769097)

标准模式：

```text
用 sentence / small chunk 做检索
命中后返回 parent window
保留命中 sentence 作为 anchor
```

不是：

```text
先召回 paragraph
再把整个 parent context 丢给模型
```

正确交付：

```text
anchor sentence + parent context
```

对应我们的问题：

```text
q002 gold paragraph 在 evidence
但 gold sentence 没被 highlight
```

我们缺的不是 parent context，而是：

```text
anchor sentence
```

---

## 4. Contextual Retrieval

来源：

- [Anthropic Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Claude Cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)

做法：

```text
chunk 前拼接文档级上下文
再 embedding / BM25
```

解决的问题：

```text
chunk 离开上下文后语义不完整
```

局限：

```text
主要提升召回
不解决 evidence 排序和 highlight
```

结论：

```text
可以继续做
但不能指望它修 evidence 0.65/0.75
```

---

## 5. Late Chunking

来源：

- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://export.arxiv.org/abs/2409.04701v2)

核心：

```text
先让长上下文模型编码全文
再对 token embedding 做 chunk pooling
```

优点：

```text
chunk 表示保留全局上下文
```

局限：

```text
索引层优化
不直接解决 evidence 组装
```

---

## 6. Submodular Evidence Selection

来源：

- [Submodular Evidence Selection for Grounded Answer Generation, TREC RAG 2025](https://trec.nist.gov/pubs/trec34/papers/WING-II.rag.pdf)
- [What Survives Into Context: Budget-Constrained Multi-Hop RAG](https://ar5iv.labs.arxiv.org/html/2607.00725)
- [SCES-RAG: Semantic Evidence Selection](https://dl.acm.org/doi/10.1007/978-981-92-3426-4_8)

核心：

```text
不是简单 Top-K
在 token/evidence 预算下
最大化相关性 + 覆盖度 - 冗余
```

对应我们的问题：

```text
parent_context 太长
highlight 膨胀
evidence 顺序打乱
```

建议：

```text
evidence budget = 3–5 个 anchor
每个 anchor 最多 1 个 parent section
不把 30 条 sentence 全塞进去
```

---

## 7. Stage-wise Evaluation

来源：

- [CLEAR-RAG: A Practical Framework for Evaluating Production-Grade RAG](https://zenodo.org/records/20110205/files/CLEAR-RAG%20A%20Practical%20Framework%20for%20Evaluating.pdf)
- [CFDA at TREC 2025 RAG](https://trec.nist.gov/pubs/trec34/papers/cfdalab.rag.pdf)

强调分开评估：

```text
retrieval
context relevance
faithfulness
answer quality
```

对应我们的四层：

```text
L1 raw paragraph
L2 evidence paragraph
L3 evidence sentence
L4 evidence nDCG
```

---

## 8. Lost in the Middle

来源：

- [Inhibitory Attention for Clinical Long-Context Reasoning](https://export.arxiv.org/pdf/2608.20348)
- 长上下文 “lost in the middle” 研究

结论：

```text
关键证据的位置会影响模型使用
```

对应我们的数据：

```text
raw nDCG     .6965
evidence nDCG .4571
```

不是 gold 不在，而是：

```text
gold 在 evidence 里的位置变差
```

建议：

```text
evidence 按 anchor rerank score 排序
关键 anchor 放前面
parent context 只作为支撑
```

---

## 9. 我们之前失败的方案

尝试：

```text
全局 sentences_fts 补 200 条
每个 paragraph 补 1 条
```

结果：

```text
q002 仍不命中
q002 highlight 膨胀到 36 条
```

原因：

```text
补的是“全库相关句”
不是“当前 evidence 的 anchor sentence”
```

结论：

```text
不能从全库补高亮
只能从当前 evidence 的 paragraph 内选 anchor
```

---

## 10. 建议的最终组装模型

```text
候选：paragraph / sentence
  ↓
rerank
  ↓
每个候选保留 anchor sentence
  ↓
parent context 只做支撑
  ↓
submodular 选 3–5 个 anchor
  ↓
evidence 顺序 = anchor rerank 顺序
  ↓
highlight = anchor sentence
```

关键约束：

```text
anchor 必须来自当前候选
不能从全库 FTS 补
parent context 不能反向决定 highlight
```

---

## 11. 对 G2 的直接影响

```text
问题不在 pgvector
不在 entity/MMR/RRF
在 evidence 的 canonical unit
```

下一步必须做：

```text
G2.6 anchor sentence 选择
G2.7 evidence ordering
G2.8 submodular evidence packing
G2.9 four-layer evaluation
```

---

## 12. 参考链接

- [Anthropic Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Claude Cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- [Late Chunking](https://export.arxiv.org/abs/2409.04701v2)
- [LangChain ParentDocumentRetriever](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/)
- [Submodular Evidence Selection, TREC RAG 2025](https://trec.nist.gov/pubs/trec34/papers/WING-II.rag.pdf)
- [What Survives Into Context](https://ar5iv.labs.arxiv.org/html/2607.00725)
- [SCES-RAG](https://dl.acm.org/doi/10.1007/978-981-92-3426-4_8)
- [CLEAR-RAG](https://zenodo.org/records/20110205/files/CLEAR-RAG%20A%20Practical%20Framework%20for%20Evaluating.pdf)
- [CFDA TREC 2025 RAG](https://trec.nist.gov/pubs/trec34/papers/cfdalab.rag.pdf)
- [Lost in the Middle 相关研究](https://export.arxiv.org/pdf/2608.20348)
