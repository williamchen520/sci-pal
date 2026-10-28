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

## 6. 自适应模式（推荐）

```powershell
$env:SCIPAL_CONTEXTUAL_MODE = "adaptive"
```

- 简单问题：原 `paragraphs`；
- 复杂问题：`paragraphs_contextual`。

### 100 题（top10）

| 指标 | 基线 | adaptive | 全量 contextual |
|---|---|---|---|
| sentence strict Recall | 0.5365 | **0.5885** | 0.6719 |
| paragraph Recall | 0.6146 | **0.6823** | 0.7656 |
| sentence-in-paragraphs | 0.7500 | 0.7604 | 0.8229 |
| refusal | 0.75 | **0.75** | 0.50 |

### 30 题（top10）

| 指标 | 基线 | adaptive |
|---|---|---|
| sentence strict | 0.5192 | 0.5192 |
| paragraph | 0.7692 | 0.7885 |
| sentence-in-paragraphs | 0.8462 | 0.8462 |
| refusal | 0.75 | 0.75 |

## 6.1 adaptive + QA 预算（100 题）

| 分层 | 预算 | Recall | paragraph_sentence | refusal |
|---|---|---|---|---|
| simple | 10 | 0.4200 | 0.6600 | 0.75 |
| simple | 20 | 0.5300 | 0.7400 | 0.50 |
| complex | 10 | **0.7717** | 0.8696 | — |
| complex | 20 | **0.7717** | 0.8913 | — |

结论：complex 层用 contextual 后 Recall 从 0.663 提到 0.7717；top20 不再提升 strict，但 coverage 略升。

## 7. 结论

- adaptive：strict +9.7%（100 题），拒答保持 0.75；
- 全量 contextual：strict +25.2%，拒答降到 0.50；
- 默认仍关闭；高召回场景可用全量，日常问答建议 adaptive。

## 8. 为什么不全量默认

全量 contextual 的拒答代价明显；adaptive 是当前召回/拒答最平衡的模式。

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
