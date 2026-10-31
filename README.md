# SciPal — 科研文献 RAG 系统

本地化部署的科研文献检索、结构化解析与综述生成系统。核心是**确定性检索层**
（向量 + FTS5/BM25 + RRF 融合 + Cross-Encoder 重排 + 查询路由 + 自适应上下文扩展），
生成层推荐**本地小模型做调度 + 云端/DSH 模型做推理**。

> 当前版本：**V33.96**（2026-10-31）
> Python 3.12 · Flask · ChromaDB · SQLite · OpenAI 兼容云端 / Ollama
> 原生 HTML/CSS/JS 前端（无框架），DSH 可作为可选推理层

---

## ⚠️ 【极其重要：开发中（WIP）警告】 ⚠️

1. 本项目目前处于重度开发阶段（Work In Progress），尚未发布任何正式 Release 版本。
2. 当前主分支代码包含大量未修复的 Bug、不稳定的接口以及未经过全量测试的逻辑。
3. 绝对禁止将当前代码直接部署于任何生产环境、医疗/科研关键业务或涉及重要数据的场景！
4. 任何无视本警告、擅自将开发中代码用于实际生产导致的数据丢失、系统崩溃等重大损失，均由使用者自行承担全部法律与经济责任。作者概不负责！

---

## ⚠️ 大规模/并发测试强制要求

> **进行大规模（>100 篇）测试或并发测试时，必须使用 PostgreSQL 底座，严禁使用 SQLite 进行高并发测试。**
>
> **SQLite 只允许用于本地小规模功能验证（≤100 篇、单进程），且必须显式设置 `SCIPAL_BENCH_ALLOW_SQLITE=1`。**

Benchmark 默认连接串：

```text
postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
```

可通过以下环境变量覆盖：

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "postgresql://user:pass@host:5432/db"
```

小规模本地验证才允许：

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "sqlite:///data/bench_local.db"
$env:SCIPAL_BENCH_ALLOW_SQLITE = "1"
```

说明：

- 当前业务数据库仍是 SQLite；PostgreSQL 业务后端尚未实现。
- 本策略是 **fail-fast**：没有 PostgreSQL 后端时，大规模/并发 benchmark 会直接失败，而不是悄悄退回 SQLite。
- 详见 [docs/benchmark-PostgreSQL策略.md](docs/benchmark-PostgreSQL策略.md)。

---

## 功能概览

| 能力 | 说明 |
|---|---|
| 本地文献检索 | 向量 + FTS5 双路召回，RRF 融合，Cross-Encoder 重排，段落→整节扩展 |
| 结构化解析 | PDF 三引擎（Docling / GROBID / MinerU）+ JATS XML 原生结构化导入 |
| 章节/段落/句子树 | `sections` 显式父子，段落绑定 `section_id`，句子带 page/bbox |
| 引用与图表位置 | 句子 ↔ 引用/图/表（`sentence_links`，含来源与置信度） |
| 句子溯源 | `/api/papers/<id>/trace` + 高亮裁剪图 + `frontend/trace.html` |
| RAG 问答 | 证据信封 + 引用；本地 7B / 云端模型可切换 |
| Adaptive Contextual | 简单问题用原段落索引，复杂问题用 contextual 索引；默认开启 |
| 句子种子 | `sentences_fts` 召回段落候选；`SCIPAL_SENTENCE_SEEDS=1` 可提高召回，延迟约 3.6× |
| 领域自适应 | `domain_profiles` + `paper_domains` + 软路由；默认关闭，供后续监控/简报复用 |
| 答案级评测 | 异步 QA + coverage / citation / refusal；100 题云端 coverage 0.7733、refusal 1.00 |
| 外部评测 | SciFact 100 claims：doc recall 0.97 / sentence recall 0.97 / MRR 0.828；LitQA2 20 题 smoke |
| 拒答与 grounding | 领域化拒答、词重合 / cross-encoder / LLM grounding 均保留为实验开关 |
| QA 预算自适应 | 简单/复杂均默认 top10；`SCIPAL_QA_COMPLEX_TOPK=20` 可提高复杂问题覆盖 |
| 综述生成 | 大纲 → 按章节检索分配 → 分章生成 → 证据-声明矩阵 → 迭代评分 |
| 在线检索与下载 | PubMed / PMC 在线检索，异步下载、增量入库、队列/历史/重试 |
| 文献源 | Europe PMC 批量、arXiv/bioRxiv/medRxiv、Crossref/OpenAlex/Unpaywall |
| 元数据回填 | Crossref DOI → Crossref 标题 → OpenAlex 标题，全库覆盖率 99.9%+ |
| 文章图谱 | `paper_links`：cites / cited_by / similar |
| 文献监控 | 多 profile、期刊发现、增量抓取、去重、周报、条目反馈、`watch-cron` 定时调度 |
| 多用户与隔离 | users / workspaces / memberships；role=owner/pi/member/viewer；paper/note/project/experiment 隔离 |
| 项目与实验 | 项目成员、实验、两级 run、修订、字段审计、电子签名、PI 访问请求 |
| 领域包 | 声明式 pack（taxonomy / section types / evidence schema / prompts）；`/packs.html` |
| Claim 试点 | Claim Card、qualifiers、正反证据、FTS/语义检索、NLI、裁决事件、writing brief |
| 插件端口 M0/M1/M2 | `services/plugins` + `plugins/` manifest/port schema/adapter；JSONL provenance；ClaimVerifier + Retriever 端口 |
| Benchmark DB 策略 | 默认 PostgreSQL URL；>100 篇/并发禁用 SQLite；小规模需显式 opt-in |
| DB adapter P1 | SQLite 默认；PostgreSQL schema + adapter opt-in；不迁移数据、不切换读路径 |
| 部署 | Docker Compose（app + watch-cron + Caddy）、备份、离线 bundle |
| 实验方案 | Protocols.io 实时检索/导入；Dockstore / bio.tools / nf-core |

## 架构

![SciPal 芯片架构图](docs/图-SciPal芯片架构.png)

详细模块、路由与数据流图见 **[docs/架构与路由图.md](docs/架构与路由图.md)**。

```
DSH 桌面 / 浏览器
   │ MCP / HTTPS
   ▼
Flask API（routes/* 26 个蓝图，约 180 条路由）
   │
services/*（检索、问答、综述、guard、源适配）
   │
build_db/*（解析、JATS 导入、结构重建、写库）
   │
SQLite research.db + ChromaDB + documents/ + documents_xml/
```

## 技术栈

- 后端：Python 3.12 · Flask 3 · flask-cors · pydantic 2 · networkx
- 检索：ChromaDB · sentence-transformers · FTS5(BM25) · RRF · bge-reranker
- PDF：PyMuPDF · Docling · GROBID · MinerU（按需，质量门兜底）
- XML：PMC / Europe PMC JATS（`<sec>` / `<ref-list>` / `<xref>`）
- LLM：云端 OpenAI 兼容 API（推荐推理）+ 本地 Ollama（调度/兜底）；DSH 可接管推理
- 前端：原生 HTML/CSS/JS + PDF.js（viewer / compare / trace / projects / reviews / watch / packs / claims）
- 部署：Docker Compose（app + watch-cron + Caddy）· SQLite 单节点 · G 盘数据卷

### 模型

| 模型 | 用途 |
|---|---|
| `deepseek-chat`（云端） | 推荐：问答、综述、claim 校验 |
| `qwen2.5:3b` | 本地轻量：意图、路由、调度 |
| `qwen2.5:7b-instruct-q4_K_M` | 本地兜底：离线问答/综述（Q4 量化） |
| `BAAI/bge-base-en-v1.5` | 向量嵌入 |
| `BAAI/bge-reranker-base` | Cross-Encoder 重排 |
| `scispacy en_ner_bionlp13cg_md` | 生物医学实体识别 |
| Docling / TableFormer | 版面、表格、章节 |
| MinerU 4.x | 扫描件/复杂版式兜底 |
| GROBID（CRF/Full） | 元数据、结构化引用、正文引用位置 |

## 数据规模（research.db）

| 表 | 数量 |
|---|---|
| papers | 3,297（JATS XML 3,214 + PDF 83） |
| paragraphs | 167,283 |
| sentences | 862,114（PDF 句级 bbox 58,648） |
| sections | 69,097 |
| citations | 182,758（91.5% 有句级位置） |
| figures / tables | 13,458 / 4,920 |
| sentence_links | 296,867（JATS 291,857 + GROBID 3,292） |
| paper_links | 164,802 |

## 快速开始

```powershell
# 1. 依赖
python -m venv venv_sciPal_py312
venv_sciPal_py312\Scripts\pip install -r requirements.txt

# 2. 启动 Flask（5000）
venv_sciPal_py312\Scripts\python.exe api_server.py

# 3. 解析服务（可选，PDF 三引擎）
powershell -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1

# 4. 测试（带连续失败止损）
venv_sciPal_py312\Scripts\python.exe scripts\run_tests_guarded.py

# 等价标准命令（不含止损）
venv_sciPal_py312\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

常用环境变量：

```powershell
# 推荐：云端推理
$env:SCIPAL_LLM_PROVIDER = "openai"
$env:SCIPAL_LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:SCIPAL_LLM_MODEL = "deepseek-chat"
$env:SCIPAL_LLM_API_KEY = "sk-..."

# 或：本地 Ollama（离线/调度）
$env:SCIPAL_LLM_PROVIDER = "ollama"
$env:SCIPAL_LLM_MODEL = "qwen2.5:7b-instruct-q4_K_M"

$env:SCIPAL_GROBID_URL = "http://127.0.0.1:8070"
$env:SCIPAL_GROBID_URL_FULL = "http://127.0.0.1:8071"
$env:MINERU_HOME = "D:\mineru_home"
```

## 目录结构（当前）

```
sci-pal/
├─ api_server.py             Flask 入口（注册蓝图，仅剩静态路由）
├─ routes/                   26 个蓝图：core/search/papers/reviews/qa/watch/claims/...
├─ services/
│  ├─ search/                混合检索、rerank、上下文扩展、源适配
│  ├─ qa/                    问答、证据信封
│  ├─ review/                综述生成、LLM 客户端、任务
│  ├─ watch/                 profile / run / digest / scheduler
│  ├─ domain_packs/          pack loader / validator / CLI
│  ├─ claims/                retrieval / semantic / nli / service
│  ├─ plugins/               contracts / registry / runner
│  ├─ tenancy/               users / workspaces / roles
│  ├─ projects/ experiments/ 项目 / 实验 / run / 审计 / 签名
│  ├─ quality/               guard、术语校验
│  └─ pdf/ workflow/ utils/
├─ build_db/
│  ├─ parsers/               docling / grobid / mineru / pipeline
│  ├─ jats_parser.py         JATS 解析
│  ├─ import_jats.py         结构化导入（含 sentences）
│  ├─ structure_v2.py        章节/句子/图谱迁移
│  ├─ sentence_geometry.py   句子 bbox
│  ├─ rebuild_sentence_links.py
│  ├─ watch_schema.py        watch 表
│  ├─ claim_pilot_schema.py  claim 表
│  └─ audit_structure.py     结构完整性审计
├─ mcp_server/               search / generate / guard（MCP 薄转发）
├─ packs/                    领域包（biomed-oncoimmuno）
├─ plugins/                  插件 manifest / port schema / adapter
├─ eval/                     检索/QA/插件对比脚本（plugin_bench、claim_verifier_bench、retriever_bench）
├─ frontend/                 viewer / compare / trace / projects / reviews / watch / packs / claims
├─ docs/                     架构、数据、设计文档
├─ tests/                    735 项测试
├─ documents/                PDF
├─ documents_xml/            JATS XML
├─ data/                     research.db、chroma
└─ scripts/                  服务启动脚本
```

## API 分组

| 组 | 前缀 |
|---|---|
| 认证/工作区 | `/api/auth/*` `/api/workspaces/*` |
| 检索 | `/api/retrieve` `/api/search/*` |
| 论文 | `/api/papers/*`（解析、PDF、附件、标注、trace） |
| 问答 | `/api/qa/*` `/api/agentic/*` |
| 综述 | `/api/review/*` `/api/reviews/*` |
| 文献监控 | `/api/watch/*` |
| 领域包 | `/api/domain-packs/*` |
| Claim | `/api/claims/*` |
| 项目/实验 | `/api/projects/*` `/api/experiments/*` `/api/runs/*` |
| 质量 | `/api/guard/*` |
| 入库/任务 | `/api/ingest/*` `/api/tasks/*` |
| 其他 | `/api/protocols/*` `/api/references/*` `/api/abstracts/*` |

完整路由以 `routes/` 与 `api_server.py` 为准，架构见 [docs/架构与路由图.md](docs/架构与路由图.md)。

## 测试

```
735 tests, ~68s
```

覆盖：检索、路由、guard、结构、JATS 导入、watch、domain packs、claim 试点、多用户隔离、项目/实验/run、插件端口。

## 文档

- [架构与路由图](docs/架构与路由图.md)
- [PDF 三引擎联合解析](docs/PDF解析-三引擎联合.md)
- [文献源与 JATS 导入](docs/文献源-JATS与外部源.md)
- [多用户与数据隔离计划](docs/工作计划-多用户与数据隔离.md)
- [去学科化与领域包分发计划](docs/工作计划-去学科化与领域包分发.md)
- [自适应与文献情报计划](docs/工作计划-自适应与文献情报.md)
- [项目跟踪与实验记录计划](docs/工作计划-项目跟踪与实验记录.md)
- [DSH 适配与插件化计划](docs/工作计划-DSH适配与插件化.md)
- [论证工作台改造计划](docs/工作计划-论证工作台改造.md)
- [插件端口与对比评测计划](docs/工作计划-插件端口与对比评测.md)
- [Benchmark PostgreSQL 策略](docs/benchmark-PostgreSQL策略.md)
- [PostgreSQL 迁移计划](docs/工作计划-PostgreSQL迁移.md)
- [跨平台路径体检报告](docs/跨平台路径体检报告.md)
- [Windows 开发警示与跨平台规范](docs/Windows开发警示与跨平台规范.md)
- [PostgreSQL 迁移基线](docs/PostgreSQL迁移-基线.md)
- [PostgreSQL FTS 对齐实验](docs/PostgreSQL迁移-FTS对齐实验.md)
- [PostgreSQL FTS porter 20 query](docs/PostgreSQL迁移-FTS-porter-20query.md)
- [PostgreSQL P4 元数据双写](docs/PostgreSQL迁移-P4-双写.md)
- [PostgreSQL P5 读路径 Canary](docs/PostgreSQL迁移-P5-读路径Canary.md)
- [PostgreSQL P4 健康检查](docs/PostgreSQL迁移-P4-health.json)
- [PostgreSQL ETL dry-run](docs/PostgreSQL迁移-ETL-dryrun.json)
- [PostgreSQL ETL verify](docs/PostgreSQL迁移-ETL-verify.json)
- [PostgreSQL ETL checksum](docs/PostgreSQL迁移-ETL-checksum.json)
- [肿瘤免疫领域包](packs/biomed-oncoimmuno/README.md)
- [Claim 试点第一轮审讯记录](docs/claim-pilot-审讯记录-01.md)
- [Claim 试点反例标注](docs/claim-pilot-反例标注-01.md)
- [Claim 试点语料扩展](docs/claim-pilot-语料扩展-01.md)
- [Claim 试点在线入库](docs/claim-pilot-在线入库-01.md)
- [QA 答案级评测](docs/QA答案级评测.md)
- [SciFact 适配器](docs/评测-SciFact适配器.md)
- [LitQA2 适配器](docs/评测-LitQA2适配器.md)
- [云端模型评测](docs/云端模型评测.md)
- [可选项与用户配置](docs/可选项与用户配置.md)
- [部署（Docker Compose）](deploy/README.md)
- [协作规范](docs/协作规范.md)
- [AI 最高优先级规则 `.dsh_rules`](.dsh_rules)
- [历史文档归档](docs/archive/README.md)

## 许可证

本项目采用 **GNU Affero General Public License v3.0 only**（AGPL-3.0-only）。

- 许可证全文：[LICENSE](LICENSE)
- 版权：Copyright (C) 2026 williams / SciPal contributors
- 说明与义务：[docs/许可证说明.md](docs/许可证说明.md)

> 若你修改后通过计算机网络提供服务，AGPL §13 要求向用户提供对应源码；
> 闭源商用需另行取得 PyMuPDF、MinerU 等依赖的商业授权。

## 已知限制

1. XML 论文无 bbox（格式本身无坐标）；MinerU 兜底路径也无 bbox；
2. 未被正文提及的图表、未被引用的参考文献没有位置；
3. 旧 PDF 的 GROBID 位置已回填 42 篇，个别 PDF 无正文引用标记；
4. Europe PMC 搜索服务 503 时无法继续扩量；
5. PDF 章节树来自解析推断，XML 才是原生结构；
6. 多用户/隔离已实现，但仍是 SQLite 单节点；1000 账号/100 并发需 PostgreSQL + Redis + 多 worker；
7. 100 题中 69 题是 auto 生成题，coverage 0.686，仍是主要拖累；
8. DSH 插件化仍为方案，尚未实现 MCP evidence / validate 工具；
9. 云端评测/生成会把论文文本发送到外部 provider，正式使用前需确认数据合规；
10. Claim 试点仅覆盖 10 个 HCC claim；writing_brief 只有 1 个 claim 完成；
11. 在线 ingest 只完成 2 篇（LEAP-012 / EMERALD-1 解读）；PMC13036683 下载失败；
12. 写作闸门仍是 brief + 人工检查，尚未自动拒绝违规句子；
13. 插件端口为 M0/M1/M2：可信插件进程内执行，尚未做 subprocess/container 隔离；Retriever 已接入，C 阶段 PaperGenerator 未实现；
14. PostgreSQL 业务后端尚未实现：benchmark 默认 fail-fast 指向 PostgreSQL，小规模本地测试需显式 `SCIPAL_BENCH_ALLOW_SQLITE=1`。

---

## Development Note（开发手记）

SciPal 的 15 万行底座，是由人类架构师提供设计规范与 5 条核心开发规则，并与 DSH 智能体在数千次高频交互中逐步演化而成。我们证明了：在极致的工程纪律与清晰的架构契约下，大模型能够保持‘零幻觉、零钝化’的高效输出，成为最可靠的开发伙伴。
