# ContextExpander 重构计划

> 状态：进行中  
> 目标：把“段落命中的窗口拼接器”升级为“句子最小单元 + 章节树 + token 预算”的上下文构建器。

## 1. 暂时搁置的进度

以下工作已完成或已进入主线，暂不再投入：

- 全量 Contextual 段落索引（164,654 段）；
- Adaptive Contextual 默认开启（简单原索引、复杂 contextual）；
- 100 题：strict Recall 0.5365 → 0.5885，refusal 0.75；
- 段落级证据契约 `paragraph_details`；
- QA 段落引用 + citation fallback；
- 综述工作流（PICO/筛选/PRISMA/证据表/RoB/HTML/PDF/Word）；
- 工程铁律、PR 模板、里程碑数据表。

以下暂缓：

- 全量 RAPTOR 多级 LLM 摘要树；
- 云端 provider 评测；
- 端到端 QA 批量评测（本地 7B 延迟过高）。

## 2. 问题

当前 `ContextExpander`：

```
段落 hits → 按 section 分组 → 固定 12 段/窗口 → 每段 1 个 highlight 句子
```

与数据结构不匹配：

- 最小单元是句子，但种子是段落；
- 固定窗口/段落数，未用 `path/depth`；
- 每段只回 1 句，strict sentence Recall 被限制；
- 线性 envelope，丢失 paper/section/paragraph/sentence 层级；
- citation links 未参与扩展。

## 3. 设计

### 3.1 Node 契约

```python
Node(
  id, level,            # sentence | paragraph | section | paper
  parent_id, children,
  text, sentence_ids,
  path, depth, tokens,
  score,
)
```

### 3.2 扩展流程

1. **Seed**：段落/句子 hybrid + rerank；
2. **Ancestor closure**：向上补 paragraph/section；
3. **Descendant selection**：在 section 内按 token 预算选段落/句子；
4. **Diversity**：section 级 MMR；
5. **Structured envelope**：保留 paper/section/paragraph/sentence ID。

### 3.3 预算

- 目标上下文：1200–2000 tokens；
- 每条句子/段落有 token 估算；
- 贪心选择，避免固定“10 段/10 句”。

### 3.4 参数

```
SCIPAL_CONTEXT_MODE=tree      # 新旧切换
SCIPAL_CONTEXT_TOKENS=1200
SCIPAL_CONTEXT_SECTIONS=4
SCIPAL_CONTEXT_PARAS=4
SCIPAL_CONTEXT_SENTENCES=2
```

## 4. 验收指标

- `sentence strict Recall@10`
- `paragraph Recall@10`
- `sentence-in-paragraphs`
- `refusal_accuracy`
- 上下文 token 数
- 延迟

在 30/100 题上与旧 expander A/B；没有稳定收益则不默认启用。

## 5. 迁移步骤

1. 新增 `services/search/tree_context.py`；
2. `UnifiedRetriever` 按 `SCIPAL_CONTEXT_MODE` 选择 builder；
3. 保留旧 `ContextExpander`；
4. 结果写入 `eval/results/`；
5. 评估后再决定默认值与 PR。

## 6. 风险

- token 预算过小会丢上下文；
- 每段多句会挤占 top10；
- section 级 MMR 可能降低段落多样性；
- 旧/新 envelope 字段不兼容。

## 7. 第一轮试验结果（未达预期）

30 题对比：

| 方案 | top10 sentence Recall | paragraph Recall | refusal |
|---|---|---|---|
| 旧 ContextExpander | **0.5192** | **0.7692** | 0.75 |
| tree（4 sections / 4 paras / 2 sent） | 0.3462 | 0.5192 | 0.75 |
| tree（10 sections / 2 paras / 1 sent） | 0.4615 | 0.7115 | 0.75 |

结论：

- section-first 选段会丢掉段落级精确排序；
- 旧 expander 的“按命中段落分组 + 每段 1 句”在 strict Recall 上仍最优；
- 第一轮 tree builder **不默认启用**，`SCIPAL_CONTEXT_MODE=tree` 仅保留实验。

## 7.1 第二版：anchor-preserving 结果

| 数据集 | 指标 | 旧 expander | tree v2 |
|---|---|---|---|
| 30 题 | sentence strict@10 | 0.5192 | 0.5192 |
| 30 题 | paragraph@10 | 0.7692 | **0.7885** |
| 30 题 | sentence-in-paragraphs | 0.8462 | 0.8269 |
| 30 题 | refusal | 0.75 | 0.75 |
| 100 题 | sentence strict@10 | 0.5885 | 0.5885 |
| 100 题 | paragraph@10 | 0.6823 | 0.6823 |
| 100 题 | sentence-in-paragraphs | 0.7604 | 0.7240 |
| 100 题 | refusal | 0.75 | 0.75 |

结论：

- anchor-preserving 修复了“上下文预算挤掉 anchor”的问题；
- strict Recall 与旧 expander 完全一致，没有提升；
- paragraph 在 30 题略好，但 100 题持平，coverage 反而下降；
- tree v2 仍不默认启用。

## 8. 下一步修正方向

- 保留 top paragraph hits 作为 anchor，不先按 section 重排；
- 每个 anchor 只选 1 句，周围段落只作为上下文，不参与 top10 句子；
- 用 token 预算补上下文，而不是替换命中段落；
- 然后重新 A/B。

## 9. 后续

- 稳定后接 citation graph 扩展；
- 再考虑多级 LLM 摘要树（RAPTOR）；
- 最后做云端 provider 评测。
