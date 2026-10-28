# AGENTS.md — public 文献会话（云端）

> 工作区模板：文献检索、证据包、综述；模型可用云端大模型。

## 规则

1. 只用 SciPal 的证据作答：`search_evidence` / `get_context` / `ask_question`。
2. 每个事实陈述必须带证据 ID（`[P1]`、`[F2]`）。
3. 生成后必须调用 `verify_answer`；`ok=false` 时标注为草稿，不得当作正式结论。
4. 冲突结论必须按 `[文献, 章节, 原文引用, 限定条件]` 列出，禁止融合。
5. 不把本地 raw 数据带到本会话。

## 推荐流程

```text
search_evidence(query, top_k=8)
get_context(sentence_id=...)        # 需要时下钻
verify_answer(answer, evidence_ids) # 必须
```

## 输出

- 正式结论：`verify_answer.ok=true`
- 草稿：`ok=false`，附 `warnings`
