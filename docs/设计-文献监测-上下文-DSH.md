# SciPal 设计：文献监测 + 上下文完整性 + DSH 前端替代

> 状态：方案定稿；S1 / Watch P1 / DSH 接入已实现（2026-10-28）

## 实现状态

| 模块 | 状态 |
|---|---|
| 结构索引 v3（path/depth、索引、sentences_fts） | ✅ 已实现并迁移（69,097 节） |
| 证据包 / get_context / verify_answer | ✅ 已实现 |
| 正式结论阻断 | ✅ QA 返回 answer_status=formal/draft |
| Watch P1（profile/期刊发现/运行/摘要入库/简报/已读） | ✅ 已实现 |
| Watch OA 全文入库（P2） | ✅ 已实现（Europe PMC OA JATS 优先，失败回退摘要） |
| DSH headless（MCP base/token、签名 URL、Range） | ✅ 已实现 |
| 页面裁剪（S3） | ⏳ 待做 |
| 多用户 / owner | ⏳ 以后 |
> 本文合并三块内容：新增「文献监测（Watch）」功能、上下文完整性改造、DSH 前端替代与 headless 部署。
> 三者相互关联：Watch 依赖上下文证据包与 verify_answer；DSH 是 Watch 与检索的统一前端。

## 0. 总览

```
用户（DSH 桌面）
   │  MCP / HTTPS
   ▼
SciPal（GPU 服务器，headless）
   ├─ 检索 + 结构索引（章节/段落/句子/图表/引用）
   ├─ 证据包（带上下文与 bbox）
   ├─ 校验（guard / 引用 / 冲突结构）
   ├─ Watch 调度（按领域、期刊、指标监测新文献）
   └─ 入库（OA 全文 / 非 OA 摘要）
        │
        ▼
DSH 大模型生成 → verify_answer → 正式结论 / 草稿
```

核心原则：

1. 向量负责“语义召回”，结构索引负责“确定性上下文与溯源”；
2. 生成交给 DSH，SciPal 只出证据与校验；
3. `verify_answer` 失败阻断正式结论，草稿可展示；
4. 前端只保留 PDF viewer（+ 对比页），其余任务由 DSH + MCP 替代。

---

# 1. 文献监测（Watch）

## 1.1 目标

按用户设定的研究领域、期刊范围与指标，每 N 天自动发现新文献，筛选最相关的 1–5 篇，
全文或摘要入库，生成简报：DSH 推 Top 3，前端看全部。

## 1.2 决策

| 维度 | 决定 |
|---|---|
| Profile | 多套，覆盖不同领域，独立调度与去重 |
| 间隔 | 默认 3 天，可配；运行窗口 `max(interval_days, 7)` 天 |
| 领域 | 自由文本 + 最多 5 个 OpenAlex Topic，可并用 |
| 期刊 | 自动发现领域 Top N（默认 30，可配）+ 手动 ISSN，并集去重 |
| 指标 | SJR（Scimago CSV）或 OpenAlex `2yr_mean_citedness`，可设下限 |
| 数量 | 每次 1–5 篇（默认 3）；同刊最多 2 篇，候选不足可放宽到 3 并标注 |
| 全文 | OA：JATS/PDF 全文；非 OA：仅摘要+元数据，也进简报 |
| 去重 | DOI/PMID/PMCID/标题指纹；摘要级允许后续升级全文 |
| 推送 | DSH 只推 Top 3；前端 `/watch` 看全部 |
| 已读 | 手动标记；未读（new/shown）下次窗口可补入 |
| 心跳 | 连续 30 天无推送时发一次“本月无新增” |
| 语言 | 跟随 profile（zh/en） |

## 1.3 领域与期刊发现

输入：

```
field_text             自由文本
openalex_topic_ids     最多 5 个
keywords               可选，仅召回
journal_mode           auto | manual | auto+manual
top_journal_count      默认 30
```

流程：

1. 有 Topic → 按 Topic 取 OpenAlex Sources；
2. 有 `field_text` → 检索 OpenAlex Topic，取 Sources；
3. 两者都有 → 并集去重，Topic 优先；
4. 按配置指标排序，取前 `top_journal_count`；
5. 与手动 ISSN 求并集，减去排除项；
6. 保存最终集合，标记来源（auto/manual/union）。

期刊主数据：

```
journal_catalog(issn_l, name, openalex_source_id,
                sjr, sjr_quartile, metric_year, works_count)
```

- SJR：每年从 Scimago 免费 CSV 导入；
- OpenAlex：`2yr_mean_citedness` 缓存，季度刷新；
- 指标缺失按中位数处理，不直接淘汰；
- 匹配以 ISSN-L 为准。

## 1.4 运行流水线

```
1. 窗口 [now - max(interval,7d), now]
2. 按期刊集合 + 关键词/Topic 构造查询（Europe PMC / PubMed / Crossref）
3. 拉取窗口内新文章 + 本 profile 未读
4. 去重（强标识 → 标题指纹 → watch_seen）
5. 打分 → MMR → 同刊限 2 → Top max_items
6. 入库：JATS / PDF / 仅摘要
7. 生成简报（一次 LLM 调用）
8. 写 runs/items，更新 seen
9. 推送：有新入选 → DSH Top 3；无新增 → 记录
```

打分：

```
score = 0.40 语义相似度（profile embedding vs 标题+摘要）
      + 0.20 关键词 BM25
      + 0.15 期刊指标分位
      + 0.10 新近度
      + 0.15 早期引用/Altmetric（可选）
```

- profile embedding = `field_text` + Topic 名称；
- MMR λ=0.7；
- 同刊计数在贪心选择时检查。

## 1.5 入库形态

| 情况 | acquisition | 全文索引 | 简报 |
|---|---|---|---|
| OA + JATS | `fulltext` | 段落/句子/引用 | 是 |
| OA + PDF | `fulltext` | 三引擎 | 是 |
| 非 OA | `abstract` | 不进全文索引 | 是，标注“仅摘要” |
| 后续变 OA | `fulltext`（升级） | 补建 | 历史简报不改 |

## 1.6 简报

```
【文献监测】<profile> · 2026-10-27
候选 12，入选 5（同刊限 2），新增全文 2 / 摘要 3，未读 4

1. <标题>｜<期刊>（SJR 2.1）｜2026-10-25｜全文
   为什么选：与领域高度相关；关键词命中 4/5
   概括：……（仅基于摘要/全文，guard 校验）
2. …｜仅摘要
3. …

全部 5 篇与历史：/watch?profile=<id>&run=<id>
```

规则：每期一次 LLM 调用；只基于摘要/全文；过 guard；语言跟随 profile。

## 1.7 调度与心跳

- 每个 profile 独立 `next_run_at`，错峰；
- 全局串行队列，避免同时打爆外部 API；
- 无新增：`status='empty'`，不推送；
- 距上次推送 ≥30 天且本月未发心跳：推一次“本月无新增”；
- EPMC 503：退避，标记 `partial`，下轮补。

## 1.8 数据模型

```sql
watch_profiles(
  id, name, field_text, keywords, openalex_topic_ids,
  interval_days DEFAULT 3, window_days DEFAULT 7,
  top_journal_count DEFAULT 30, max_items DEFAULT 3,
  same_journal_limit DEFAULT 2,
  metric_type, metric_min, language, delivery, enabled,
  last_run_at, next_run_at, last_push_at, last_heartbeat_at
)

watch_profile_journals(profile_id, issn_l, name, source, added_at)

watch_runs(
  id, profile_id, window_start, window_end, status,
  found, selected, imported_full, imported_abstract, skipped,
  digest_md, error, started_at, finished_at
)

watch_items(
  id, run_id, profile_id, paper_id, doi, title, journal, published,
  score, reason, acquisition, status, read_at
)

watch_seen(profile_id, dedup_key, paper_id, first_seen_at, status, read_at)
```

去重键：`doi:` → `pmid:` → `pmcid:` → `title:sha1(normalized)`。

## 1.9 API

```
GET/POST/PUT/DELETE /api/watch/profiles[/<id>]
POST   /api/watch/profiles/<id>/run
GET    /api/watch/profiles/<id>/runs
GET    /api/watch/runs/<run_id>
GET    /api/watch/runs/<run_id>/digest.md
GET    /api/watch/topics?q=...
GET    /api/watch/journals?profile=<id>
POST   /api/watch/items/<id>/read
POST   /api/watch/runs/<id>/read-all
```

---

# 2. 上下文完整性改造

## 2.1 现状

- 检索粒度是**段落**：Chroma 为 paragraphs/papers/figures/tables，无 sentences；
- `ContextExpander` 已做 small-to-big（按 `section_level1` 取整节/窗口）；
- 命中标记 `▶…◀` 在源码里是乱码，需改 ASCII；
- `to_envelope` 带章节名与页码，但未用 `sections` 树、无句子高亮；
- `sentences`（char_start/end、bbox）未被检索层使用；
- 生成本地 qwen，无冲突条款、无 `verify_answer`。

## 2.2 结构索引（物化路径）

```
sections.path   TEXT   -- "1.3.2"
sections.depth  INTEGER
```

```sql
idx_sections_parent     ON sections(paper_id, parent_id, seq)
idx_sections_path       ON sections(paper_id, path)
idx_paragraphs_section  ON paragraphs(section_id, sequence)
idx_sentences_section   ON sentences(section_id, sequence)
idx_figures_number      ON figures(paper_id, fig_number)
idx_tables_number       ON tables(paper_id, table_number)
idx_citations_number    ON citations(paper_id, ref_number)
```

另补 `sentences_fts`。迁移：加列 → 递归回填 path/depth → 审计；重导入重算。
后续量上来加 `section_closure(ancestor_id, descendant_id, depth)`。

## 2.3 证据包

```json
{
  "evidence_id": "P1",
  "paper": {"paper_id": "...", "title": "...", "journal": "...", "year": 2026},
  "section_path": ["3 结果", "3.2 疗效分析"],
  "page": 6,
  "paragraph": "……完整段落……",
  "highlight": [{"sentence_id": "...", "text": "...", "bbox": "51,58,204,66"}],
  "neighbors": {"before": "...", "after": "..."},
  "links": [
    {"target_type": "citation", "target_id": "...", "doi": "...", "source": "grobid", "confidence": 0.9},
    {"target_type": "figure", "target_id": "...", "fig_number": "Fig 2"}
  ]
}
```

规则：命中段 + 前后各 1 段；完整祖先标题；超预算退化为窗口 ±2 段；高亮用 `【HIT】…【/HIT】`；PDF 带 bbox，XML 只给文本位置。

## 2.4 冲突铁律

```
不同文献/段落结论冲突时，禁止融合成模糊结论。
必须按 [文献, 章节, 原文引用, 限定条件] 列出；
限定条件缺失标注“原文未说明”；输出必须含 conflicts 数组。
```

## 2.5 MCP 契约

```
search_evidence(query, top_k=8)          → 结构化证据包
get_context(paper_id, sentence_id|para_id, before=1, after=1)
verify_answer(answer, evidence_ids)      → 校验报告
```

校验报告：

```json
{
  "ok": false,
  "missing_ids": ["P9"],
  "uncited_claims": ["..."],
  "quote_mismatch": ["P2"],
  "guard": {"unknown_ratio": 0.02},
  "conflict": {"structure_ok": false, "missing_conditions": ["P3"]},
  "warnings": ["..."]
}
```

规则：引用 ID 存在 + 原文子串匹配；冲突四要素；guard 阈值；校验器不调 LLM。
失败：`ok=false` → 正式结论阻断，草稿可展示。

## 2.6 生成流程

```
DSH → search_evidence → DSH 模型生成 → verify_answer
  ok=true  → 正式输出/落库
  ok=false → 草稿 + 原因
```

本地 qwen 保留 fallback。

## 2.7 改动清单

| 文件 | 改动 |
|---|---|
| `services/search/context_expander.py` | sections 递归路径；`expand_sentence`；窗口 ±1；ASCII 标记 |
| `services/search/unified_retriever.py` | envelope 带路径/高亮/bbox/邻段；`to_evidence_json` |
| `services/qa/qa_service.py` | 拆 `build_evidence()`/`generate()`；冲突条款；外部生成 |
| `services/qa/validator.py` | 冲突结构、限定条件、引用子串、覆盖率 |
| `mcp_server/search_server.py` | `search_evidence` / `get_context` / `verify_answer` |

---

# 3. DSH 前端替代与 headless 部署

## 3.1 页面依赖（现状）

```
index ─► qa
qa ─► review, compare
review ─► reviews, index
reviews ─► review, references, tasks, index
protocols/references ─► reviews
paper ─► reviews（无入链，孤儿）
compare ─► viewer
viewer ◄── 仅 compare 引用
trace ◄── 无入链
```

## 3.2 保留与下线

保留：

```
viewer.html + compare.html + trace.html
frontend/vendor/pdf.min.js（替换 CDN）
/api/papers/<id>/pdf
/api/papers/<id>/annotate(s)
```

下线（MCP 工具齐后）：

```
index qa review reviews tasks protocols references paper
```

## 3.3 拓扑

```
GPU 服务器（Linux）
  ├─ SciPal API（headless）
  ├─ worker（解析/入库，GPU 串行）
  ├─ Chroma + research.db + documents/
  ├─ GROBID / MinerU（容器）
  └─ viewer（唯一 Web 页面）

桌面
  └─ DSH 桌面版
       └─ MCP scipal-* → HTTPS → 服务器 API
```

## 3.4 远程 MCP

```
SCIPAL_API_BASE=https://scipal.example.internal
SCIPAL_API_TOKEN=***
```

stdio 在本机；无需远程 MCP 传输。

## 3.5 鉴权

- MCP/API：`Authorization: Bearer <token>`；
- viewer/PDF：短时签名 URL（`?token=...&expires=...`）；
- 公网：反代 TLS + 限流；局域网/VPN 同样 token。

## 3.6 PDF 流式 + Range

```
curl -H "Range: bytes=0-1023" /api/papers/<id>/pdf
→ 206 + Content-Range
```

viewer 改用 `/vendor/pdf.min.js`，不依赖 CDN。

## 3.7 服务器

- systemd：api、worker、watchdog；
- 容器：GROBID CRF/Full、MinerU；
- 数据：research.db、documents/、data/chroma 本地盘 + 备份；
- GPU 串行：解析与检索共用 GPU，需要队列/锁。

## 3.8 多用户（暂不做）

- 不加 `user_id`，写操作预留 `owner`（可空）；
- 任务 `params` 放 owner；
- 将来 DSH 服务器版再加鉴权、配额、隔离。

## 3.9 分阶段

| 阶段 | 内容 |
|---|---|
| S1 | MCP base/token；viewer 本地 pdf.js；Range 206 |
| S2 | 服务器部署（systemd + 反代 + 数据迁移）；DSH 桌面接入 |
| S3 | 删 legacy 页面；静态资源只留 viewer 所需 |
| S4 | 以后：DSH 服务器版多用户 + owner |

---

# 4. 三者如何协同

## 4.1 Watch 的一次运行

```
DSH 定时任务 → watch_run(profile)
  → SciPal 检索/去重/打分 → 入库（全文或摘要）
  → 生成简报草稿（本地 LLM 或返回证据包）
  → DSH 生成/润色 → verify_answer
       ok=true  → 正式简报 + Top 3 推送
       ok=false → 草稿 + 原因，不推送正式版
```

## 4.2 用户点开某条监测结果

```
DSH → get_context(paper_id, sentence_id)
  → 章节路径 + 段落 + 高亮句 + 图表/引用
  → DSH 可再下钻（相邻段、整节）
  → 需要原文 → 打开 viewer 签名 URL
```

## 4.3 数据流

```
Watch 入库 → papers / sections / paragraphs / sentences
           → sentence_links（引用/图表位置）
检索 → 结构索引 + 向量 → 证据包
生成 → DSH → verify_answer → 正式/草稿
```

---

# 5. 风险与待确认

## 5.1 风险

1. 章节 path 重导入需重算，旧数据要回填；
2. 旧 XML 论文仍有约 9 千句无 section_id（已回填 15 万条）；
3. DSH 无法替代 PDF 标注，viewer 必须保留；
4. 公网暴露需 TLS、token、限流、审计；
5. GPU 单卡下解析与检索互相排队；
6. EPMC 搜索服务可能 503，Watch 需退避与 `partial`。

## 5.2 待确认

1. `sentences_fts` 放在 S1 还是结构索引迁移时一起做；
2. viewer 签名 URL 的有效期（建议 10 分钟）；
3. Watch 简报的 LLM 由 DSH 生成还是 SciPal 本地生成（建议 DSH，失败回退本地）。
