# Google CoE（Chain-of-Evidence）对照与借鉴

> 日期：2026-10-31  
> 性质：设计对照文档，不含代码改动  
> 结论先行：Google 公开的 `generated-artifacts` 是**产物归档**，不是 CoE 框架代码；SciPal 应借“产物级溯源 + 断言级证据链”的分层，而不是复刻 autonomous research。

---

## 1. 本次核查范围

### 1.1 已核查仓库

```text
https://github.com/scientist-one/generated-artifacts
```

本地克隆后检查：

```text
21 个 PDF
146 个 .py
130 个 .json
87 个 .txt
12 个 .md
5 个 .yaml
1 个 .sh
4 个 .out
4 个 .jsonl
```

仓库只有 1 个 commit，没有 README，没有框架入口。

### 1.2 已检索关键词

在全部文本文件中搜索：

```text
evidence
Chain-of-Evidence
claim
verif
```

结果：

```text
没有 CoE 实现
没有 claim 结构
没有 evidence chain 字段
没有 citation verifier
```

### 1.3 参考但未能全文打开的公开材料

- [Google Research: Science One Framework via Chain-of-Evidence](https://research.google/blog/science-one-framework-a-verifiable-autonomous-research-framework-via-chain-of-evidence/)
- [ScientistOne 论文页](https://ar5iv.labs.arxiv.org/html/2605.26340)
- [ScientistOne 项目页](https://scientist-one.github.io/)
- [AlphaSignal 报道](https://alphasignal.ai/news/google-cloud-s-scientistone-writes-ai-research-papers-with-zero-hallucinated)

> 这些页面在当前网络下无法稳定打开全文，因此本文把“仓库事实”与“公开描述”分开写，不把推断当事实。

---

## 2. 仓库里到底有什么

### 2.1 目录

```text
generated-artifacts/
├─ generated-papers/
│  ├─ adrs/    15 篇 PDF
│  ├─ mle/     5 篇 PDF
│  └─ pg/      1 篇 PDF
├─ solution-code/
│  ├─ adrs/    15 个 .py
│  ├─ mle/     各任务的代码、日志、指标、ablation
│  └─ parameter-golf/
└─ LICENSE     Apache-2.0
```

### 2.2 元数据

`state.json` / `metrics.json` / `agent_log.txt` 显示的是任务执行产物：

```text
task
constraints
iteration
branch
best_idea
best_score
evaluation_metrics
swarm_feedback
artifacts
```

流水线阶段可以从日志中看到：

```text
ideator
  ↓
solver
  ↓
evaluator
  ↓
branch / iteration
  ↓
paper artifacts
```

### 2.3 生成的论文

抽取 PDF 文本后检查：

```text
常规 ML 论文结构
有 References
有 Limitations
没有 evidence / claim / citation verifier 字段
没有 GitHub / code availability 链接
```

结论：

> 这个仓库证明“论文 + 代码 + 指标可以一起交付”，  
> 但不能证明“每个 claim 都被证据链验证”。

---

## 3. 两个必须区分的层级

### 3.1 Artifact provenance（产物级溯源）

```text
论文
  ↔ solution code
  ↔ metrics
  ↔ run / branch / iteration
```

回答：

```text
这篇论文对应哪份代码？
这个指标来自哪个 run？
这个 run 属于哪个 branch？
```

### 3.2 Claim evidence chain（断言级证据链）

```text
claim / 句子
  ↔ evidence span
  ↔ 论文 / 图表
  ↔ study type / endpoint
  ↔ 反例 / 限定条件
```

回答：

```text
这句话为什么能由这条证据支持？
这条证据的方法和终点是否匹配？
有没有反例？
```

SciPal 的主线是 3.2，不是 3.1。  
3.1 可以借，但不能替代 3.2。

---

## 4. 可确认的 CoE 设计信号

以下来自公开摘要/项目页描述，属于“设计信号”，不是仓库代码：

1. **claim-grounded 写作**
   - 公开描述提到 Paper Writer 采用五阶段 claim-grounded pipeline；
   - 先有 claim/evidence，再生成段落，而不是先写再补引用。

2. **零幻觉引用**
   - 公开报道强调 zero hallucinated references；
   - 引用必须真实存在，不能生成不存在的 DOI/作者/年份。

3. **证据链是核心产物**
   - 不是“引用列表”，而是“结论 → 证据 → 来源”的链。

4. **完整 autonomous research loop**
   - 选题、实验、分析、写作一体；
   - 这部分不属于 SciPal 的目标。

> 重要限制：以上不能替代对 CoE 代码的逐行阅读。  
> 如果后续拿到官方框架代码，应重新核对本文第 2、4 节。

---

## 5. SciPal 现状对照

| CoE 概念 | SciPal 现状 | 差距 |
|---|---|---|
| Claim | `claim_cards.claim_text` | 已有 |
| Qualifier | `qualifiers_json` | 已有 |
| Evidence span | `quote` + `node_id` | 已有 |
| Relation | supports / refutes / mentions / underdetermines | 已有 |
| Warrant / Backing | 字段存在 | 未强制 |
| Rebuttal | `rebuttal` / `strongest_counter` | 未强制 |
| Study type | 无 | 缺 |
| Endpoint | 无 | 缺 |
| Chain status | 无 | 缺 |
| Chain audit | 无 | 缺 |
| Writing brief | 仅 `claim_hcc_triple_os` | 覆盖不足 |
| Artifact provenance | 无（论文库场景不同） | 不优先 |

---

## 6. CoE-lite 设计建议

### 6.1 数据模型

在 `claim_card_evidence` 上增加：

```text
study_type    RCT / retrospective / meta-analysis / case report / preclinical
endpoint      OS / PFS / ORR / safety / biomarker
direction     positive / negative / null / mixed
source_scope  abstract / results / discussion / figure / table
verified_by   nli / human / rule
```

在 `claim_cards` 上增加：

```text
chain_status  complete / partial / broken
```

### 6.2 chain_status 定义

```text
complete:
  至少 1 条 support
  + 至少 1 条 refute 或 1 次明确“未找到反例”的检索记录
  + 所有断言句有 evidence_id
  + endpoint / study_type 已填
  + 人工裁决完成

partial:
  有 support，但缺反例检索 / 缺 endpoint / 缺方法学信息

broken:
  断言句没有 evidence_id
  或 quote 无法在原文中定位
  或 relation 与 NLI 结果冲突
```

### 6.3 chain_audit 检查规则

```text
A1 evidence 存在且 quote 可定位
A2 relation 合法（refutes 必须有直接矛盾理由）
A3 contested claim 必须有 support + counterevidence
A4 endpoint / study_type 与 claim 的 qualifier 匹配
A5 每个断言句有 evidence_id
A6 writing_brief 的 must_not_write 不被违反
```

输出：

```json
{
  "claim_id": "claim_hcc_triple_os",
  "chain_status": "partial",
  "support": 2,
  "refute": 1,
  "underdetermine": 5,
  "missing": ["endpoint 方法学信息", "部分断言句缺 evidence_id"],
  "writing_allowed": false
}
```

---

## 7. 以 claim_hcc_triple_os 为例

```text
claim:
  TACE + 抗 VEGF/TKI + PD-1/PD-L1 较 TACE 单药提高 OS

support:
  meta-analysis 总览 / 结果段

refute:
  LEAP-012 / EMERALD-1 解读：OS 未成熟，无显著 OS 获益

underdetermine:
  5 条边界证据

qualifier:
  PFS 与 OS 必须分开

writing_brief:
  safe_claim / must_include / must_not_write

当前 chain_status:
  partial

原因:
  有 support + refute，但 endpoint / study_type 未结构化；
  写作仍依赖人工检查，未自动阻断。
```

结论：

```text
不是“证明无效”
是“不能无条件写 OS 获益”
```

---

## 8. 不建议照搬的部分

1. **autonomous research 全流程**
   - SciPal 不做一键科研。

2. **复杂图数据库**
   - 先用 SQLite + chain_status / chain_audit。

3. **“引用存在 = 证据支持”**
   - 必须保留 NLI、refutes、人工裁决。

4. **把生成的论文当作验证器**
   - 这个仓库的论文是产物，不是验证逻辑。

---

## 9. 下一步

建议顺序：

```text
1. 先实现 chain_status + study_type/endpoint/direction（只读审计）
2. 再做 chain_audit API
3. 最后接 Writing Gate
```

每个阶段一个 PR，不合并主题。

---

## 10. 参考

- [generated-artifacts 仓库](https://github.com/scientist-one/generated-artifacts)
- [Google Research CoE 博客](https://research.google/blog/science-one-framework-a-verifiable-autonomous-research-framework-via-chain-of-evidence/)
- [ScientistOne 论文页](https://ar5iv.labs.arxiv.org/html/2605.26340)
- [ScientistOne 项目页](https://scientist-one.github.io/)
