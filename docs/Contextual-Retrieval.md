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

## 3. 当前状态

- 构建脚本已完成；
- 查询开关已完成；
- 全量构建 164,654 段，预计约 **2 小时**（RTX 4060）；
- 当前只完成 5,120 段，未做基准对比，**不宣称提升**。

## 4. 为什么先停

- 全量构建时间超出单轮；
- 在完成全量前，不能公平对比 Recall；
- 已有 paragraph_recall 0.7692、contract-level 0.8462，说明段落召回本身不是主要瓶颈。

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
