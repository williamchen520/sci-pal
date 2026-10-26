# scipal-guard P1：实体词表校验

> 数据：`D:\sci-pal\pubtator3\`（WorkBuddy 拉取，476 篇 / 10,386 条标注）
> 代码：`services/quality/lexicon.py`、`services/quality/guard.py`、`routes/guard.py`
> 结论：实体类可判，方法与主题短语不判；真实综述 0 unknown、误报已收敛到可接受范围。

---

## 1. 数据画像（必须先记住的硬限制）

| 项 | 值 |
|---|---|
| 语料论文 | 476 篇（本地库去重后的 PMCID） |
| PubTator3 标注 | 10,386 条，463/476 篇有标注（97.3%） |
| **只有标题+摘要** | 475 篇（`full=true` 仅 1 篇）→ **词表里没有 ≠ 论文里没有** |
| 标注类型 | Disease 4,640 / Gene 2,608 / Chemical 1,619 / Species 1,475 / Variant 28 |
| 词表条目（type+ID） | 2,050；可用候选 1,829（去 Species/Chromosome/RefSeq/CellLine） |
| 候选分布 | Gene 724 / Disease 640 / Chemical 450 / Variant 15 |
| 单篇出现 | **1,367 条（75%）**——只能算「见过」，不能当权威 |
| 同面多 ID | 2,553 个 surface 中 78 个有歧义（AS、PD-L1、STAT3、IL-6…） |
| 泛词 | tumor 168 篇、inflammatory 128 篇、infection/toxicity 等 |

两条硬限制：

1. PubTator 只标**标题+摘要**，正文术语不在词表里；
2. PubTator 只标**实体**，不标方法/技术（CRISPR、Western blot 均 0 命中），对方法类发难全是误报；
3. 作者 keywords 命中词表仅 24.8%（主题短语居多），不能当覆盖率指标。

## 2. 三源分工（P1 口径）

| 来源 | 判什么 | 实现 |
|---|---|---|
| PubTator3 词表 | 实体是否存在、是否歧义 | `Lexicon`（curated / broad / weak 三层） |
| `paragraphs_fts` | 正文里是否出现过 | `FtsLanding`（`MATCH '"term"'`） |
| 不判 | 方法、技术、主题短语 | — |

## 3. 词表分层与匹配规则

- **curated**：papers ≥ 2、canonical 长度 ≥ 3、非泛词 → 权威；
- **broad**：tumor / inflammation / infection / failure… → 永不发难；
- **weak**：单篇出现 → 不进入匹配（避免 "and"/"as" 这类噪声）；
- 短词（≤3 字符）只有全大写才匹配（避免 AS = ankylosing spondylitis 撞 "as"）；
- 同一 surface 多个 ID → `ambiguous`（如 STAT3、STING），不判错；
- canonical 精确命中 → 视为 `known_curated`（TLR4 这类即使只标了 1 篇也是真词）。

## 4. 接口

```
POST /api/guard/check   {text} → {checked, unknown, unknown_ratio, counts, issues}
GET  /api/guard/stats   → 条目数、可匹配 surface 数、按类型/分层统计
GET  /api/guard/term/<term> → 标准 ID、aliases、papers、tier
```

工作流 verify 阶段默认调用 guard，`verify.json` 多一个 `vocabulary` 段（不影响引用校验）。

实测（p15b，15 句 / 29 条证据的综述）：

```
checked 34 | unknown 0 | curated 31 | broad 3 | ambiguous 5
verify 阶段耗时 163 ms（引用校验 + guard）
```

## 5. 误报处理记录

| 现象 | 处理 |
|---|---|
| "and"、"as"、"associated" 被当成疾病/基因 | 弱词不参与匹配 + 常用词表 |
| "failure" 命中 heart failure | 加入常用词表（failure/injury/pain/shock/stroke…） |
| "tumor" 被 canonical 精确命中盖过 broad | broad 判定优先于精确命中 |
| TLR4 被判 weak（只标 1 篇） | canonical 精确命中 → curated |

## 6. 已知限制

- 词表只覆盖 476 篇的标题+摘要，正文实体需要靠 FTS 兜底（会落到 `corpus` 状态）；
- `undefined_abbrev` 仅对**全大写** token 生效，且被词表/FTS 命中会放行；
- 未做跨句指代、未做物种消歧（human/mouse 同 surface 多 ID → ambiguous）；
- 未接入 MCP server（`scipal-guard` 规划为第四个 stdio server，P2/P3 再做）。

## 7. 下一步（P2）

1. 引入 HGNC / MeSH 官方词表，补全基因与疾病的规范 ID；
2. 歧义消解：按语料中该 surface 的论文主导类型（Gene/Disease）投票；
3. `SCIPAL_GUARD_MODE=warn|block` 阈值策略；
4. 前端综述页显示 guard 徽章；
5. MCP server `scipal-guard` 三个工具。
