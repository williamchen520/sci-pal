# 摘要层（RAPTOR 精简版）

> 目标：在段落检索之外增加“章节摘要”通道，用于综述型/多跳问题的定向。
> 当前实现是**抽取式**（无 LLM），可复现、零模型成本；向量化后续再加。

## 1. 表

```sql
summaries(
  summary_id, paper_id, section_id, level, title, text, token_count, created_at
)
summaries_fts(summary_id, paper_id, section_id, title, text)
```

## 2. 构建

```powershell
python -m build_db.build_summaries                  # 全库
python -m build_db.build_summaries --limit 2000     # 子集
```

摘要规则：

- 标题 + 首段第一句 + 末段第一句（去重）；
- 截断 600 字；
- 只做“定位”，不作为最终证据；回答仍需引用段落。

## 3. 检索

`services/search/summary_search.py`：

- FTS5 关键词检索；
- 支持 `paper_id` 限定；
- 已接入 `UnifiedRetriever`：`qa` 通道时返回 `summaries`，信封中标记 `[S1]`。

## 3.1 LLM 摘要（试点）

```powershell
python -m build_db.build_llm_summaries --limit 100 --model qwen2.5:3b
```

- 只改写摘要文本，不重建表；
- `summary_source='llm'` 区分抽取式；
- 试点：100 节（其余 61,832 节仍为 extractive）。

## 3.2 向量通道

```powershell
python -m build_db.build_summary_vector_index            # 全库
python -m build_db.build_summary_vector_index --limit 5000
```

- Chroma collection：`section_summaries`；
- embedding：`bge-base-en-v1.5`（`SCIPAL_EMBEDDING_MODEL` 可覆盖）；
- 默认不启用，设置 `SCIPAL_SUMMARY_VECTOR=1` 后 `UnifiedRetriever` 优先用向量摘要命中。

## 4. 当前状态

- 已构建 61,932 个章节摘要（全库；100 节为 LLM 生成）；
- 已构建 61,932 节摘要向量（全库，3,054 篇）；
- 重建：`python -m build_db.build_summaries`；
- 测试：`tests/test_summaries.py`。

## 4.1 基准（E1 30 题）

| 指标 | 向量前 | 向量后 |
|---|---|---|
| recall@10 | 0.5192 | 0.5192 |
| MRR | 0.3331 | 0.3331 |
| nDCG@10 | 0.3532 | 0.3532 |
| refusal | 0.75 | 0.75 |

结论：摘要向量通道**没有改变段落证据的 Recall@10**。  
原因：top-3 摘要命中的 section 多数已被段落检索覆盖，新增证据为 0；  
摘要命中率 `summary_hit@3 = 10/26 = 38.5%`，说明摘要检索本身可用，但尚未融合进段落排序。

## 5. 限制与下一步

- 抽取式摘要可能漏掉关键结论 → 后续用本地 3B 生成；
- 无向量检索 → 后续写入 Chroma `summaries` collection；
- 摘要不能替代证据 → `verify_answer` 仍只认段落引用；
- 需要评测：在 100 题上比较“有/无摘要通道”的 Recall@10 与延迟。
