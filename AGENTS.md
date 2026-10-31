# Sci-Pal 项目说明书（给 AI 代码助手）

> **最高优先级：先读 [`.dsh_rules`](.dsh_rules)，再读本文件。**
> 未加载规则前，不得修改代码、写数据库、创建或合并 PR。
> 违反规则必须立即报 `RULE_VIOLATION`。

> 本文件帮助 AI 代码助手快速理解项目架构、代码规范和开发约定。
> 每次修改代码前请先阅读本文件。

## 项目概述

**Sci-Pal** 是一个本地化部署的科研文献 RAG（检索增强生成）系统，用于：
- 搜索本地学术文献库（向量+BM25+实体+重排多路召回）
- 按大纲章节自动检索、分配论文、撰写综述
- RAG 学术问答
- 在线搜索 NCBI PubMed/PMC 并下载入库
- 实时搜索 Protocols.io 实验方法（不下载，API 对接）

**技术栈**：Python 3.12 + Flask + ChromaDB + Ollama（本地 LLM）+ scispacy + 原生 JS（无框架）

## 项目结构

```
sci-pal/
├── api_server.py              # Flask 主入口（端口5000）
├── config/settings.py         # 全局配置
├── services/                  # 核心业务逻辑
│   ├── search/                # 检索层（18个模块）
│   │   ├── unified_retriever.py   # 统一检索器（段落/图表/表格）
│   │   ├── hybrid_search.py        # 向量+BM25混合搜索
│   │   ├── hybrid_retriever.py     # 混合检索（本地+在线+Protocols.io）
│   │   ├── online_search.py        # NCBI PubMed/PMC 在线搜索
│   │   ├── online_downloader.py    # 在线论文异步下载入库
│   │   ├── protocols_io_client.py  # Protocols.io API 客户端
│   │   ├── reranker.py             # Cross-Encoder 重排
│   │   ├── query_expander.py       # 查询扩展
│   │   ├── sentence_relation_classifier.py  # 句子关系判定
│   │   └── retrieval_observability.py       # 检索可观测性
│   ├── review/                # 综述生成（15个模块）
│   │   ├── review_generator.py     # 综述生成主引擎
│   │   ├── evidence_extractor.py   # 证据卡片抽取+去重
│   │   ├── evidence_card_incremental_manager.py  # 证据卡片增量维护
│   │   ├── llm_client.py           # LLM 客户端（Ollama）
│   │   ├── outline_store.py        # 大纲存储
│   │   ├── citation_formatter.py    # 引用格式化
│   │   ├── citation_verifier.py    # 引用验证
│   │   ├── sentence_locator.py     # 句子定位原文
│   │   ├── user_feedback.py        # 用户反馈闭环
│   │   ├── version_manager.py      # 版本管理
│   │   ├── impact_analyzer.py      # 影响范围评估
│   │   ├── export_manager.py       # 导出分享
│   │   ├── task_manager.py         # 任务管理
│   │   └── models.py               # 数据模型
│   ├── qa/qa_service.py           # RAG 问答
│   ├── ai/ai_service.py           # AI 服务
│   ├── pdf/annotator.py           # PDF 标注
│   ├── data/version_manager.py    # 数据版本
│   └── utils/                     # 工具
│       ├── retry_utils.py         # 重试机制
│       └── structured_logger.py  # 结构化日志
├── routes/                    # Flask 路由
│   ├── search_routes.py
│   ├── paper_routes.py
│   ├── ai_routes.py
│   └── writing_routes.py
├── frontend/                  # 前端（原生 JS，无框架）
│   ├── index.html             # 搜索主页
│   ├── review.html            # 综述生成页
│   ├── qa.html                # 问答页
│   ├── viewer.html            # PDF 阅读器
│   ├── compare.html           # 双栏对比
│   └── src/                   # JS 模块
│       ├── review.js
│       ├── outline_core.js
│       ├── outline_editor.js
│       ├── paper_list.js
│       ├── paper_importer.js
│       ├── pdf_viewer.js
│       └── ...
├── build_db/                  # 建库脚本（25个文件）
├── database/init_db.py       # 数据库初始化
├── prompts/                   # LLM 提示词模板
├── download_*.py              # 数据下载脚本
├── requirements.txt
├── .env.example
├── WORK_LOG.md                # 版本工作日志（重要！每次更新）
├── test_workflow.sh           # 测试工作流
├── self_check.py              # 自检脚本
└── AGENTS.md                  # 本文件
```

## 核心架构原则（必须遵守）

### 1. 检索层与数据层解耦
- **SQLite 管内部关系**（论文元数据、章节结构、证据卡片）
- **ChromaDB 管语义检索**（段落向量、摘要向量）
- 两者通过 paper_id 挂钩
- **新增数据只更新数据库和向量库，检索层代码一行都不用改**

### 2. 三层数据架构
| 层级 | 方式 | 数据源 |
|------|------|--------|
| 第一层 | 直接对接（API实时调用，不下载） | Protocols.io |
| 第二层 | API实时检索（调搜索API，不建向量库） | NCBI PubMed/PMC在线搜索、Dockstore、bio.tools |
| 第三层 | 本地建库（下载→解析→建向量索引） | PMC全文XML、PubMed摘要、Bio-protocol |

### 3. 综述生成流程（V32.1+）
1. 选择预设大纲模板（不是自动生成大纲）
2. 编辑大纲关键词
3. **按大纲章节关键词搜索并分配论文**（search_and_assign_papers）
4. 分章节生成，渐进式上下文注入
5. 证据-声明矩阵验证
6. 迭代精炼 + 5维评分

### 4. 综述生成不需要关系抽取和冲突检测
- 这些是问答功能用的
- 综述生成时直接跳过（V31.82）

## 模型配置（V33.9）

| 模型 | 用途 | 显存 |
|------|------|------|
| qwen2.5:3b | 轻量任务（生成大纲、证据抽取） | ~2GB |
| qwen2.5:7b-instruct-q4_K_M | 重量任务（写综述、问答） | ~4.5GB |
| BAAI/bge-base-en-v1.5 | Embedding | ~1.5GB |
| BAAI/bge-reranker-base | Reranker | ~1.2GB |
| **总计** | | **~7.2GB / 8GB** |

- 本地路径：`D:\models\models\BAAI--bge-base-en-v1.5` 和 `BAAI--bge-reranker-base`
- Reranker 的 config.json 必须手动加 `"model_type": "bert"`
- Ollama API：`http://localhost:11434`

## 环境变量

```bash
# .env 文件或 PowerShell 环境变量
SCIPAL_PROTOCOLS_IO_TOKEN=your_protocols_io_token
NCBI_API_KEY=your_ncbi_api_key
NCBI_EMAIL=your_email@example.com
OLLAMA_BASE_URL=http://localhost:11434
```

## 数据库路径

```
data/research.db              # 主数据库（论文元数据、证据卡片）
data/abstracts.db             # 摘要数据库
data/chroma/                  # 全文向量库（collection: sci_pal_paragraphs）
data/chroma_abstracts/        # 摘要向量库
data/protocols_io_cache/       # Protocols.io API 缓存
```

## 代码规范

### Python
- Python 3.12，类型注解（typing）
- **英文注释**（用户偏好）
- 类名用 PascalCase，函数/变量用 snake_case
- 每个模块开头有 docstring 说明功能
- 错误处理用 try/except，打印中文日志（print 带 emoji）

### 前端
- 原生 JS，不用框架（React/Vue 都不引入）
- CSS 在 frontend/src/review.css
- 模块化 JS 文件，通过 `<script>` 标签引入

### 版本号
- 格式：V33.x（主版本.次版本）
- 每次功能更新递增次版本号

## 开发约定（重要！）

### 每次修改代码后必须同步更新：
1. **WORK_LOG.md** — 追加版本记录（修改了什么、为什么、影响范围）
2. **test_workflow.sh** — 增加对应测试项
3. **self_check.py** — 增加对应检查项

### 不能做的事：
- 不要引入多智能体架构（有精确数据库不需要）
- 不要修改检索层接口来适配新数据（数据层自己适配）
- 不要删除已保存的 7 章节大纲模板
- 不要在综述生成流程里加关系抽取/冲突检测
- 不要把 Protocols.io 数据下载到本地建库（直接 API 调用）

### Git 提交规范：
- commit message 格式：`V33.x: 简要描述`
- 推送到 Gitee：`https://gitee.com/williamsucas/sci-pal`

## 启动方式

```powershell
# PowerShell
cd D:\sciPal
.\venv_sciPal_py312\Scripts\Activate.ps1
python api_server.py
# 访问 http://127.0.0.1:5000
```

## 已知问题和注意事项

1. **Windows 控制台编码**：所有打印必须用 emoji/中文，Python 脚本开头强制 `sys.stdout.reconfigure(encoding='utf-8')`
2. **GitHub API 限流**：nf-core 下载遇 403 时自动等待 60 秒重试
3. **PubMed 筛选语法**：`free full text[Filter]`，不要用 `"open access"[Filter]`（不存在）
4. **Reranker 模型**：config.json 缺 `model_type: bert` 会报 "Unrecognized model"
5. **显存**：RTX 4060 8GB，重量模型必须用 Q4 量化版，否则爆显存
6. **SQLite FTS**：查询语法注意关键词不要当列名（之前出过 "no such column: Immunity" 的错）
