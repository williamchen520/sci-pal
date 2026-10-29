# 工作计划：开源对照 + AutoMerging 验证

> 状态：进行中（本轮不 PR）  
> 目标：先对照开源做法，再验证“叶子检索 + parent merge”，不继续堆叠未经验证的融合。

## 1. 背景

现有结果：

| 方法 | 结果 |
|---|---|
| Contextual adaptive | strict +9.7% |
| Sentence seeds | strict +3.6%，延迟 3.6× |
| Section routing | 30 题下降 |
| TreeRouter | strict 无提升 |

结论：问题不在“树结构不够复杂”，而在**候选生成与父级合并策略**。

## 2. 开源对照

### RAPTOR
- 递归摘要树；
- 查询时 collapsed tree：所有层节点一起检索；
- 不是从根 BFS/DFS。

借鉴：section summary / paragraph / sentence 可统一检索，命中后再补上下文。

### LlamaIndex AutoMergingRetriever
- 先检索叶子 chunk；
- 同一父节点命中足够多子节点时，合并为父节点；
- 标准 small-to-big / parent merge。

借鉴：先命中句子/段落，再按 section 命中数合并上下文。

### GraphRAG
- local search：实体/关系；
- global search：community summaries；
- 适合主题/综述，不适合单点事实。

借鉴：事实题与综述题应走不同检索路径。

### PaperQA2
- 全文章节/chunk 检索；
- LLM 重排 + 证据选择 + 引用。

借鉴：候选之后，证据选择比树遍历更重要。

## 3. 本轮要验证的 AutoMerging

### 规则

```
先选 top paragraph anchors（保持全局顺序）
→ 按 section 统计命中数
→ 命中数 ≥ min_hits 的 section
→ 把该 section 的邻居段落加入 context
→ anchors / matched_sentences 不变
```

### 与 ContextExpander 的区别

- 只对“多段落命中”的 section 合并；
- 单段落命中仍走原窗口；
- context 不进入 top10 句子竞争。

### 参数

```
SCIPAL_AUTO_MERGE=1
SCIPAL_AUTO_MERGE_MIN_HITS=2
SCIPAL_AUTO_MERGE_TOKENS=1200
```

### 验收

- strict Recall 不下降；
- paragraph / coverage 提升；
- refusal 不变；
- 延迟增加 ≤20%。

## 4. 实验

30 题先验：

```
baseline vs +auto_merge
```

若 strict 不降且 paragraph 有提升，再跑 100 题。

## 4.1 第一轮结果

30 题：

| 指标 | baseline | +auto_merge |
|---|---|---|
| sentence strict@10 | 0.5192 | 0.5192 |
| paragraph@10 | 0.7692 | 0.7885 |
| sentence-in-paragraphs | 0.8462 | 0.8462 |
| refusal | 0.75 | 0.75 |

结论：

- strict Recall 没有变化；
- paragraph 仅 +2.5pp，与已有 ContextExpander 的 section 上下文重叠；
- auto_merge 只补充上下文，不改变 anchor，因此不会改变 top10 句子；
- 默认关闭，保留实验开关。

## 5. 非目标

- 不做纯 BFS/DFS；
- 不把 TreeRouter 重新接回候选生成；
- 不做全量融合；
- 本轮不 PR。
