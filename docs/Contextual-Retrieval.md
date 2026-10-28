# Contextual Retrieval（段落上下文索引）

> 目标：给段落 embedding 加 `paper title > section path` 前缀，缓解段落脱离章节语境的问题。

## 1. 构建

```powershell
python -m build_db.build_contextual_paragraph_index
```

- 输入：`paragraphs` 表；
- 前缀：`paper title > section_path`；
- collection：`paragraphs_contextual`；
- 模型：`bge-base-en-v1.5`。

## 2. 切换查询

```powershell
$env:SCIPAL_PARAGRAPH_COLLECTION = "paragraphs_contextual"
```

`HybridSearch` 会从该 collection 做向量召回，FTS / rerank 不变。

不设置环境变量时仍用原 `paragraphs` collection，默认行为不变。

## 3. 全量构建

```
164,654 段落（100%）
```

## 4. 100 题结果（top10）

| 指标 | 基线 | contextual |
|---|---|---|
| sentence strict Recall@10 | 0.5365 | **0.6719** |
| paragraph Recall@10 | 0.6146 | **0.7656** |
| sentence-in-paragraphs | 0.7500 | **0.8229** |
| refusal | 0.75 | 0.50 |

## 5. 30 题结果（top10）

| 指标 | 基线 | contextual |
|---|---|---|
| sentence strict Recall@10 | 0.5192 | 0.5192 |
| paragraph Recall@10 | 0.7692 | 0.7885 |
| sentence-in-paragraphs | 0.8462 | 0.8846 |
| refusal | 0.75 | 0.50 |

## 6. 结论

- Contextual 段落索引在 100 题上显著提升 strict Recall（+25.2%）；
- paragraph / sentence-in-paragraphs 也提升；
- 但拒答从 0.75 降到 0.50；
- 默认仍不启用，按“高召回场景”显式开启：

```powershell
$env:SCIPAL_PARAGRAPH_COLLECTION = "paragraphs_contextual"
```

## 7. 为什么不全量默认

拒答代价明显；下一步应把 contextual 与 sufficiency 阈值/拒答策略一起调，而不是直接切换默认。

## 5. 后续验证

```powershell
# 1. 全量构建
python -m build_db.build_contextual_paragraph_index

# 2. 启动带开关的 Flask
$env:SCIPAL_PARAGRAPH_COLLECTION = "paragraphs_contextual"

# 3. 同一 100 题
python -m eval.contract_eval --gold eval/gold/seed_100.jsonl --limit 100
```

对比 `contract_100.json` 与 contextual 结果，再决定是否默认启用。
