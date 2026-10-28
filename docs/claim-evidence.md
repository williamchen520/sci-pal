# Claim–Evidence 图（试点）

> 目标：把“结论句”和“它引用的证据句”显式存起来，为冲突检测/综述提供结构。
> 当前是**试点**：只覆盖“被引论文也在本地库”的引用。

## 1. 表

```sql
claims(claim_id, paper_id, sentence_id, claim_text, claim_type, created_at)
claim_evidence(claim_id, evidence_sentence_id, relation, confidence)
```

## 2. 构建

```powershell
python -m build_db.build_claims --limit 5000
```

规则：

1. 取带 citation 链接的句子；
2. 用 DOI 把被引文献映射到本地 `papers`；
3. 在被引论文中找与 claim 词重合最高的句子作为证据；
4. `relation` 用引用意图，`confidence` 用词重合比例。

## 3. 当前规模

```
claims  29
evidence 26
```

原因：多数被引论文不在本地库（只有 3,297 篇），DOI 无法映射。

## 4. 限制

- 只覆盖本地互引；
- 证据选择是词重合，不是语义蕴含；
- 无 LLM 验证。

## 5. 下一步

1. 用标题/作者模糊匹配扩展被引论文映射；
2. 对被引论文做“摘要级入库”，至少拿到标题+摘要；
3. 用 3B 模型判断 claim 与证据是 support/contrast；
4. 把 claim 图接入综述写作：每段必须挂 claim_id。
