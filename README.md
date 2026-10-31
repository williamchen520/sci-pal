# SciPal — 科研文献 RAG 系统

本地化部署的科研文献检索、结构化解析与综述生成系统。核心是**确定性检索层**
（向量 + FTS5/BM25 + RRF 融合 + Cross-Encoder 重排 + 查询路由 + 自适应上下文扩展），
生成层推荐**本地小模型做调度 + 云端/DSH 模型做推理**。

> 当前版本：**V33.96**（2026-10-29）
> Python 3.12 · Flask · ChromaDB · SQLite · OpenAI 兼容云端 / Ollama
> 原生 HTML/CSS/JS 前端（无框架），DSH 可作为可选推理层

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
| 文献监测（设计） | 多 profile、领域 Top 期刊、SJR/OpenAlex、DSH 推 Top 3（未实现） |
| 实验方案 | Protocols.io 实时检索/导入；Dockstore / bio.tools / nf-core |

## 架构

![SciPal 芯片架构图](docs/图-SciPal芯片架构.png)

详细模块、路由与数据流图见 **[docs/架构与路由图.md](docs/架构与路由图.md)**。

```
DSH 桌面 / 浏览器
   │ MCP / HTTPS
   ▼
Flask API（routes/* 17 个蓝图，98 条路由）
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
- 前端：原生 HTML/CSS/JS + PDF.js（viewer/compare/trace）

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

# 4. 测试
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
├─ routes/                   15 个蓝图：core/search/papers/reviews/qa/guard/...
├─ services/
│  ├─ search/                混合检索、rerank、上下文扩展、源适配
│  ├─ qa/                    问答、证据信封
│  ├─ review/                综述生成、LLM 客户端、任务
│  ├─ quality/               guard、术语校验
│  └─ pdf/ workflow/ utils/
├─ build_db/
│  ├─ parsers/               docling / grobid / mineru / pipeline
│  ├─ jats_parser.py         JATS 解析
│  ├─ import_jats.py         结构化导入
│  ├─ structure_v2.py        章节/句子/图谱迁移
│  ├─ sentence_geometry.py   句子 bbox
│  ├─ rebuild_sentence_links.py
│  └─ audit_structure.py     结构完整性审计
├─ mcp_server/               search / generate / guard（MCP 薄转发）
├─ packs/                    领域包（biomed-oncoimmuno）
├─ frontend/                 viewer / compare / trace / projects / reviews / watch / packs / claims
├─ docs/                     架构、数据、设计文档
├─ tests/                    669 项测试
├─ documents/                PDF
├─ documents_xml/            JATS XML
├─ data/                     research.db、chroma
└─ scripts/                  服务启动脚本
```

## API 分组

| 组 | 前缀 |
|---|---|
| 检索 | `/api/retrieve` `/api/search/*` |
| 论文 | `/api/papers/*`（解析、PDF、附件、标注、trace） |
| 问答 | `/api/qa/*` `/api/agentic/*` |
| 综述 | `/api/review/*` `/api/reviews/*` |
| 质量 | `/api/guard/*` |
| 入库/任务 | `/api/ingest/*` `/api/tasks/*` |
| 其他 | `/api/protocols/*` `/api/references/*` `/api/abstracts/*` `/api/experiments/*` |

完整 98 条路由见 [docs/架构与路由图.md](docs/架构与路由图.md)。

## 测试

```
592 tests, ~25s
```

覆盖：检索、路由、guard、结构 v2、JATS 导入、文献源、trace API、解析流水线。

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
- [肿瘤免疫领域包](packs/biomed-oncoimmuno/README.md)
- [Claim 试点第一轮审讯记录](docs/claim-pilot-审讯记录-01.md)
- [Claim 试点反例标注](docs/claim-pilot-反例标注-01.md)
- [QA 答案级评测](docs/QA答案级评测.md)
- [SciFact 适配器](docs/评测-SciFact适配器.md)
- [LitQA2 适配器](docs/评测-LitQA2适配器.md)
- [云端模型评测](docs/云端模型评测.md)
- [可选项与用户配置](docs/可选项与用户配置.md)
- [部署（Docker Compose）](deploy/README.md)
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
6. 当前为单用户；多用户与鉴权待 DSH 服务器版方案落地；
7. 100 题中 69 题是 auto 生成题，coverage 0.686，仍是主要拖累；
8. DSH 插件化仍为方案，尚未实现 MCP evidence / validate 工具；
9. 云端评测会把论文文本发送到外部 provider，正式使用前需确认数据合规。
