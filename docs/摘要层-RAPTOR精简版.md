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

## 4. 当前状态

- 已构建 61,932 个章节摘要（全库）；
- 重建：`python -m build_db.build_summaries`；
- 测试：`tests/test_summaries.py`。

## 5. 限制与下一步

- 抽取式摘要可能漏掉关键结论 → 后续用本地 3B 生成；
- 无向量检索 → 后续写入 Chroma `summaries` collection；
- 摘要不能替代证据 → `verify_answer` 仍只认段落引用；
- 需要评测：在 100 题上比较“有/无摘要通道”的 Recall@10 与延迟。
