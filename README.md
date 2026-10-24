# Sci-Pal — 科研文献 RAG 助手

本地化部署的科研文献检索与综述生成系统。核心是**确定性检索层**（向量 + FTS5/BM25 + RRF 融合 + Cross-Encoder Rerank + 查询路由 + 小→大扩展 + 多查询 + MMR 去重），生成式 LLM 只作为可选表达层；支持本地库检索、按大纲自动分配论文并生成综述、RAG 学术问答、在线检索 NCBI 并下载入库、实时对接 Protocols.io 实验方法。

> 当前版本：**V33.13** · Python 3.12 + Flask + ChromaDB + Ollama 本地 LLM · 原生 JS 前端（无框架）
> 论文/段落规模以本地数据库实际统计为准，不在此写死。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 本地文献检索 | 向量 + FTS5(BM25) 双路召回，RRF 融合，Cross-Encoder 重排，查询路由，段落→整节小到大扩展，MMR 去重，图谱遍历与 Agentic 多跳 |
| 综述生成 | 选预设大纲模板 → 编辑关键词 → 按章节搜索并自动分配论文 → 分章节生成 + 渐进式上下文 → 证据-声明矩阵 → 迭代精炼评分；句子级溯源到 PDF |
| RAG 学术问答 | 基于检索证据信封作答，带引用；关系抽取/冲突检测服务于问答与分析 |
| 在线检索与下载 | NCBI PubMed/PMC 在线搜索（本地 + 在线并行、三级去重），异步下载、增量入库、下载队列/历史/重试 |
| 实验方法实时检索 | Protocols.io API 实时调用（**不下载、不建本地向量库**）；Dockstore / bio.tools / nf-core 开放 API 实时检索 |

---

## 三层数据架构

新增数据只更新数据库和向量库，**检索层代码一行都不用改**（对外接口不变）。

| 层级 | 对接方式 | 数据源 |
|------|----------|--------|
| 第一层 | API 实时调用，不落地 | Protocols.io（实验方法） |
| 第二层 | API 实时检索，不建向量库 | NCBI PubMed/PMC 在线搜索、Dockstore、bio.tools、nf-core |
| 第三层 | 下载 → 解析 → 建本地库 | PMC 全文 JATS XML、PubMed 摘要、OpenAlex 元数据、Bio-protocol |

- **SQLite** 管内部关系（论文元数据、章节结构、证据卡片、任务）；
- **ChromaDB** 管语义检索（全文段落向量、摘要向量）；
- 两者通过 `paper_id` 挂钩。

---

## 技术栈

- 后端：Python 3.12 · Flask 3.0.3 · flask-cors · pydantic 2 · networkx
- 检索：ChromaDB 0.5.5 · sentence-transformers 3.0.1 · FTS5(BM25) · RRF · Cross-Encoder Rerank
- PDF：PyMuPDF（浏览器原生渲染 + 元数据）；可选 Docling / pdfplumber / pypdf 深度解析
- LLM：本地 Ollama（默认）或任意 OpenAI 兼容云端 API
- 前端：原生 HTML/CSS/JS，PDF.js，无前端框架
- 实体识别：scispacy（问答/分析场景）

### 模型配置（V33.9，适配 8GB 显存）

| 模型 | 用途 | 约占显存 |
|------|------|---------|
| `qwen2.5:3b` | 轻量任务：生成大纲、证据抽取、引用验证 | ~2GB |
| `qwen2.5:7b-instruct-q4_K_M` | 重量任务：写综述、问答（Q4 量化） | ~4.5GB |
| `BAAI/bge-base-en-v1.5` | Embedding | ~1.5GB |
| `BAAI/bge-reranker-base` | Reranker | ~1.2GB |
| **合计** | | **~7.2GB / 8GB** |

> 重量模型必须用 Q4 量化版，FP16 7B 在 8GB 显存会爆显存。Reranker 的 `config.json` 需手动加 `"model_type": "bert"`，否则报 "Unrecognized model"。

---

## 目录结构（当前有效部分）

```
sci-pal/
├── api_server.py              # Flask 主入口（端口 5000）
├── app.py                     # 已于 2026-10-24 删除（原与 api_server.py 抢 5000 端口且路由残缺）
├── config/settings.py         # 全局配置
├── requirements.txt
├── .env.example              # 环境变量模板
├── AGENTS.md / AI_CONTEXT.md  # 给 AI 代码助手的项目说明与上下文
│
├── services/
│   ├── search/                # 检索层
│   │   ├── unified_retriever.py    # 统一检索信封（段落/图表/表格入口）
│   │   ├── hybrid_search.py         # 向量 + FTS5 + RRF 混合搜索
│   │   ├── hybrid_retriever.py      # 本地 + NCBI + Protocols.io 三路混合
│   │   ├── online_search.py         # NCBI PubMed/PMC 在线搜索
│   │   ├── online_downloader.py     # 在线论文异步下载 + 增量入库
│   │   ├── protocols_io_client.py   # Protocols.io 客户端（缓存/限速/重试）
│   │   ├── reranker.py              # Cross-Encoder 重排
│   │   ├── query_router.py          # 查询路由（qa/citation/figure/method）
│   │   ├── query_expander.py        # 多查询 / HyDE
│   │   ├── context_expander.py      # 小→大扩展（段落 → 整节）
│   │   ├── mmr_diversifier.py       # MMR 去重
│   │   ├── graph_traverser.py       # 图谱遍历（CITES/SIMILAR 扩展）
│   │   ├── agentic_search.py        # Agentic 多跳检索
│   │   ├── retrieval_observability.py  # 检索链路可观测性
│   │   └── sentence_relation_classifier.py  # 句子关系判定
│   ├── review/                # 综述生成
│   │   ├── review_generator.py      # 综述主引擎（分章节 + 渐进式上下文）
│   │   ├── evidence_extractor.py    # 证据卡片抽取 + 去重 + 置信度
│   │   ├── evidence_card_incremental_manager.py  # 证据卡片增量维护
│   │   ├── llm_client.py            # LLM 客户端（Ollama / 云端，双模型）
│   │   ├── outline_generator.py / outline_store.py  # 大纲生成与存储
│   │   ├── citation_formatter.py / citation_verifier.py  # 引用格式化与校验
│   │   ├── sentence_locator.py      # 句子定位原文
│   │   ├── user_feedback.py         # 用户反馈闭环
│   │   ├── impact_analyzer.py       # 影响范围评估 + 局部重算
│   │   ├── export_manager.py        # 导出与分享
│   │   ├── task_manager.py          # 任务管理
│   │   ├── relation_extractor.py / conflict_detector.py  # 问答/分析用（综述不调用）
│   │   └── models.py                # Pydantic 数据模型
│   ├── qa/qa_service.py       # RAG 问答
│   ├── ai/                    # AI 服务与证据信封
│   ├── pdf/annotator.py       # PDF 标注
│   ├── data/version_manager.py
│   └── utils/                 # retry_utils.py 统一重试 / structured_logger.py 结构化日志
│
├── frontend/                  # 原生 JS（无框架）
│   ├── index.html             # 文献检索主页
│   ├── review.html            # 综述生成与预览（句子溯源）
│   ├── qa.html                # AI 学术问答
│   ├── viewer.html            # PDF.js 阅读器
│   ├── compare.html           # 双栏论文对比
│   ├── tasks.html             # 任务列表（SSE）
│   └── src/                   # outline_editor / review.js / pdf_viewer 等模块
│
├── build_db/                  # 离线建库（解析/索引/去重/社区检测）
├── download_*.py / fetch_from_ncbi.py   # 各数据源下载脚本（见下）
├── database/init_db.py       # 建库初始化（含启动迁移）
├── prompts/                  # LLM 提示词模板
├── docs/                     # 架构总览、接口明细、变更日志、工作日志、架构图
├── self_check.py / test_workflow.sh    # 自检与测试工作流
└── data/                     # research.db / abstracts.db / chroma/（不入库）
```

### 数据下载脚本（第三层本地建库）

| 脚本 | 用途 |
|------|------|
| `download_pubmed_abstracts.py` | PubMed 摘要批量下载，建摘要库 |
| `download_pmc_xml.py` / `batch_download_pmc.py` | PMC 全文 JATS XML 批量下载，自动过滤只有摘要的文章，增量下载 |
| `download_openalex.py` | OpenAlex 免费 2 亿+ 论文元数据/摘要，关键词/期刊搜索，断点续传 |
| `download_protocols.py` | 实验方法（Protocol）专刊批量下载，多专刊 + 分类主题，摘要 XML 双下载 |
| `download_bioinformatics_methods.py` | Dockstore / bio.tools / nf-core 开放 API 实时拉取方法元数据（不建向量库） |
| `fetch_from_ncbi.py` | NCBI PubMed 元数据批量抓取（摘要/作者/单位） |

---

## 环境要求

- **Python** 3.12（虚拟环境 `venv_sciPal_py312`）
- **Ollama** 本地服务 `http://localhost:11434`，已拉取 3B 与 7B-Q4 模型；或配置 OpenAI 兼容云端 API
- 依赖：`pip install -r requirements.txt`（已有数据库跑检索/问答时，Docling 等建库依赖可不装）
- 显卡：RTX 4060 8GB（CPU 也可跑 embedding/rerank，速度较慢）
- Windows 从零重建见 `README-WINDOWS.md` / `WINDOWS-INSTALL-GUIDE.md`

### 环境变量（复制 `.env.example` 为 `.env`）

```bash
# LLM：默认本地 Ollama
SCIPAL_LLM_PROVIDER=ollama
SCIPAL_LLM_HOST=http://localhost:11434
SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b

# 或切换 OpenAI 兼容云端（DashScope / OpenAI 等）
# SCIPAL_LLM_PROVIDER=openai
# SCIPAL_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# SCIPAL_LLM_API_KEY=sk-你的key
# SCIPAL_LLM_MODEL=qwen-plus
# SCIPAL_LLM_LIGHT_MODEL=qwen-turbo

# Protocols.io 实时方法检索（可选，需要 Token）
# NCBI PubMed/PMC 当前用脚本内置默认凭证，暂未走环境变量，无需配置
SCIPAL_PROTOCOLS_IO_TOKEN=your_protocols_io_token
```

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （离线建库，仅首次/扩充数据时）下载数据 → 解析 → 建 SQLite 与向量索引
#    详见 build_db/ 脚本与 docs/架构总览.md；已有库可跳过

# 3. 启动服务
python api_server.py
# 打开 http://127.0.0.1:5000
```

Windows PowerShell：

```powershell
.\venv_sciPal_py312\Scripts\Activate.ps1
python api_server.py
```

---

## 检索层

- **双路召回**：Chroma 向量召回（cosine）+ SQLite FTS5（BM25），各取 top-k
- **RRF 融合**：Reciprocal Rank Fusion（K=60）合并两路排名；多查询变体命中分数叠加
- **Rerank**：Cross-Encoder `bge-reranker-base` 对融合候选池重排输出 top-k
- **查询路由**：规则式选择通道（qa 段落 / citation 参考文献 / figure 图表 / method 方法）
- **小→大扩展**：命中段落后按 `(paper_id, section_l1)` 拉取整节，超长退化为命中点前后窗口
- **MMR**：结果去重降冗余；**图谱遍历 / Agentic 多跳**支持跨论文扩展
- **混合检索（hybrid_retriever）**：本地库 + NCBI 在线 + Protocols.io 三路并行，三级去重统一排序

## 综述生成流程（V32.1+）

1. 选择预设大纲模板（**已去掉"自动生成大纲"按钮**）
2. 编辑大纲与章节关键词
3. 按章节关键词搜索并自动分配论文（`search_and_assign`）
4. 分章节生成 + 渐进式上下文注入
5. 证据-声明矩阵校验，迭代精炼 + 5 维评分
6. 每个句子绑定证据卡片，可点击溯源到 PDF 原文页码

> **注意**：综述生成**不调用**关系抽取与冲突检测（V31.82 起跳过）；`relation_extractor.py` / `conflict_detector.py` 只用于问答与分析场景。

---

## 主要 API 路由

完整签名、参数与响应见 `docs/接口明细.md`。

| 分组 | 路由 | 说明 |
|------|------|------|
| 健康 | `GET /api/health` | 服务与版本检查 |
| 本地检索 | `GET/POST /api/retrieve` | 统一检索信封（段落/图表/表格/邻居） |
| 混合/在线 | `GET/POST /api/search/hybrid` | 本地 + NCBI + Protocols 三路混合 |
| | `GET/POST /api/search/online` | NCBI PubMed/PMC 在线搜索 |
| | `POST /api/search/download_online` | 异步在线下载入库 |
| | `GET /api/search/download_queue` `/download_status` `/download_history` | 下载队列/状态/历史 |
| | `POST /api/search/retry_download` `/clear_download_history` | 重试/清空历史 |
| 论文 | `GET /api/papers` `/api/papers/local` `/api/papers/<id>` | 列表/本地库/详情 |
| | `GET /api/papers/<id>/graph` `/pdf` | 图谱邻居 / PDF |
| | `POST /api/papers/import` `/parse` | 导入/解析 |
| 综述 | `POST /api/review/generate` | 生成综述（异步任务） |
| | `POST /api/review/outline` `/outline/save` `GET /outline/saved` ... | 大纲生成/保存/加载/删除 |
| | `POST /api/review/search_and_assign` `/assign_papers` | 按大纲搜索分配论文 |
| | `GET /api/review/<id>` `/<id>/sentence/<sid>` | 综述详情/句子溯源 |
| | `GET /api/review/llm_status` `/running_task` `/task/<id>` `POST /cancel/<id>` | LLM 状态/任务 |
| 问答 | `POST /api/qa/ask` `GET /api/qa/status` | RAG 问答 |
| 任务 | `GET /api/tasks` `/api/tasks/<id>` `/api/tasks/<id>/events` | 统一任务表 + SSE |
| 社区/图谱 | `GET /api/communities` `/api/graph/stats` `/api/agentic/search` | 社区/图谱统计/多跳 |
| 摘要库 | `GET /api/abstracts/list` `/api/abstracts/<id>` | 摘要库浏览 |

---

## 测试与自检

```bash
python self_check.py                 # 数据库 + 检索 + 数据质量自检（必跑）
bash test_workflow.sh                # 全模块测试工作流
python -m py_compile api_server.py  # 语法检查
```

---

## 开发约定（必须遵守）

- **检索层接口不改**：`UnifiedRetriever.retrieve()` 与 `HybridRetriever.search_papers()` 签名固定，新增数据源只在内部加
- **数据库结构不随意改**：`data/research.db` 表结构变更必须走 migration
- **已保存的 7 章节大纲模板**（`data/outlines/`）不能删除
- 综述流程不引入关系抽取/冲突检测，不引入多智能体架构
- Protocols.io 只做 API 实时调用，不下载落地建库
- 每次修改代码后同步更新 `WORK_LOG.md`、`test_workflow.sh`、`self_check.py`
- 代码注释用英文；commit 信息格式 `V33.x: 简要描述`

## 文档索引

- `docs/架构总览.md` — 整体大图、模块边界、环境约束（先看）
- `docs/接口明细.md` — 全部函数签名、参数、返回值
- `docs/变更日志.md` — 版本倒序记录
- `docs/工作日志/` — 按月开发日志
- `docs/` 下 6 幅 HTML 架构图（数据流 / 分层 / PDF 解析 / 完整数据流 / 三层链路 / 增量更新子图）

---

## 版本脉络（精选）

| 版本簇 | 主要内容 |
|--------|---------|
| V20–V24 | 数据层（Docling/GROBID → SQLite + Chroma + FTS5）、混合检索/RRF/Rerank、查询路由、小→大扩展、图谱、Agentic 多跳、PDF 阅读器、社区检测 |
| V25 | 综述生成智能体、证据卡片、双 Provider、前端综述预览与句子溯源、引用格式化、自定义大纲 |
| V26 | 异步任务取消、摘要库 Tab、任务进度显示、刷新恢复任务 |
| V30 | 批量证据抽取/批量引用验证、并行抽取提速、编号核查、证据缓存落盘 |
| V31 | 本地 Ollama 双模型（3B 大纲/验证、7B 正文）、按章节写、熔断、Embedding 换 bge-base、PMC XML 独立库 + 联合索引、按大纲搜索自动分配、综述跳过关系/冲突 |
| V32 | 大纲模板化、章节关键词注入检索、分章节生成 + 渐进式上下文、证据-声明矩阵、迭代精炼评分、OpenAlex/PubMed/PMC 下载工具集、过滤只有摘要文章 |
| V33.0–V33.3 | Windows 编码修复、NCBI 在线搜索 + 三路混合检索、异步在线下载增量入库、下载队列/历史/重试/配置面板 |
| V33.4–V33.6 | EvidenceCard 去重与置信度、证据不足 fallback；检索可观测性、句子关系判定、证据卡片增量维护；反馈闭环、版本管理、影响评估局部重算、统一重试、结构化日志、导出分享 |
| V33.7–V33.9 | Protocol 专刊批量下载、生信方法开放 API、7B Q4 量化适配 8GB 显存 |
| V33.10–V33.13 | Protocols.io 实时对接、前端实验方法展示、文档体系与 VS Code 配置、统一任务表 + SSE、启动自动建表、文档入库 |

> 逐版本细节见 `docs/变更日志.md` 与 `WORK_LOG.md`。

---

## 许可

内部项目，未开源。
