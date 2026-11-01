# Sci-Pal 架构总览

> **最后更新**：V33.96 (2026-10-29)
> **维护规则**：每次版本迭代后必须同步更新此文档，确保架构信息不丢失。

---

## 一、项目总览

### 项目目标
Sci-Pal 是一个**本地学术文献管理与智能阅读系统**，核心目标是**缩短科研人员阅读文献的时间**。

### 核心能力
1. **文献解析**：PDF → 结构化数据（段落/图表/表格/参考文献/元数据）
2. **混合检索**：向量 + FTS5 + RRF 融合 + Cross-Encoder Rerank + MMR 多样性去重
3. **知识图谱**：论文间引用关系（CITES）+ 语义相似关系（SIMILAR）
4. **RAG 问答**：基于检索结果的学术问答（英文优先，带引用溯源）
5. **综述生成**：自动生成文献综述（大纲 → 证据抽取 → 冲突识别 → 撰写）
6. **PDF 阅读**：浏览器原生 iframe 渲染，三栏布局（大纲/论文/段落）

### 当前版本
**V33.96** — 云端推理 + 自适应检索 + 答案级评测收口

> 与 `VERSION` 文件保持一致；以 git 提交信息里的 `V33.x` 为准。

### V33.96 当前架构快照（2026-10-29）

#### 运行分层

```
本地小模型（Ollama）  → 意图 / 路由 / 调度 / 兜底
云端模型（DeepSeek 等）→ 答案生成 / 综述 / claim 校验 / 拒答
DSH（可选）           → 外部推理层；插件化仍在方案阶段
```

#### 检索

- **Adaptive Contextual 默认开启**：
  - 简单问题 → `paragraphs`；
  - 复杂问题 → `paragraphs_contextual`；
  - 索引缺失时自动回退。
- **Sentence seeds**：`sentences_fts` → 段落候选；`SCIPAL_SENTENCE_SEEDS=1`，默认关闭，延迟约 3.6×。
- **TreeRouter / AutoMerging / Section routing / Anchor roles**：实验开关，默认关闭；30/100 题无 strict 增益。
- **证据契约**：`paragraph_details` 带 `para_id` + `sentence_ids`；QA sources 带 `paragraph_id` / `sentence_ids`。
- **上下文扩展**：保留旧 ContextExpander；TreeContext v2 只重排不补候选。

#### 生成与拒答

- QA 默认 top10（复杂问题 `SCIPAL_QA_COMPLEX_TOPK` 可调）。
- 异步 QA：`/api/qa/ask_async` + `/api/review/task/<id>` 轮询。
- 云端答案级（100 题）：

| 指标 | 值 |
|---|---|
| coverage | 0.7733 |
| avg citations | 27.11 |
| refusal_accuracy | 1.00 |

- 拒答实验开关：
  - `SCIPAL_DOMAIN_REFUSAL`；
  - `SCIPAL_GROUNDED_ANSWER`；
  - `SCIPAL_SEMANTIC_GROUNDING`；
  - `SCIPAL_LLM_GROUNDING`；
  - 全部默认关闭。

#### 领域自适应

- 表：`domain_profiles` / `paper_domains`；
- 3,308 篇论文领域弱标签；
- 6 个领域：hcc_io / oncology_other / microbiology / endocrinology / alzheimers / general；
- `SCIPAL_DOMAIN_ROUTING=1` 软路由，默认关闭；
- 后续文献监控简报复用此层。

#### 评测体系

| 层级 | 指标 |
|---|---|
| 检索 | sentence strict Recall@10、paragraph Recall@10、sentence-in-paragraphs、refusal |
| 答案 | coverage、avg citations、refusal_accuracy |
| 实验 | 30 / 100 题；30 题仅作 smoke test |

#### 主要新增模块

- `services/search/domain_taxonomy.py`
- `services/search/domain_router.py`
- `services/search/tree_router.py`
- `services/search/auto_merger.py`
- `services/search/sentence_seeds.py`
- `services/search/sentence_roles.py`
- `services/qa/grounding.py`
- `services/qa/semantic_grounding.py`
- `services/qa/llm_grounding.py`
- `eval/qa_answer_async_eval.py`
- `build_db/build_domain_profiles.py`
- `build_db/validate_section_tree.py`

#### 当前判断

- 数据结构不是主要瓶颈；
- auto 题（69/100）coverage 0.686 是主要拖累；
- 云端推理解决了拒答问题；
- 外部评测：
  - SciFact 100 claims：doc recall 0.97、sentence recall 0.97、MRR 0.828；
  - LitQA2 20 题 smoke：13 篇获取全文、8 题可评测，样本过小；
  - 内部回归集（31 人工 + 4 拒答）继续保留。
- 下一步优先做 auto 题失败归因与 100 题引用/拒答分析。

---

## 二、目录结构

```
sciPal/
├── api_server.py              # Flask API 服务入口（主程序）
├── app.py                     # 已于 2026-10-24 删除（原与 api_server.py 争 5000 端口且路由残缺）
├── config/
│   └── settings.py            # 配置管理（可能未使用，以环境变量为主）
├── routes/                    # 蓝图路由（旧版，可能已废弃，主路由在 api_server.py）
│   ├── ai_routes.py           #   AI 问答蓝图（旧版，新版在 api_server.py）
│   ├── paper_routes.py        #   论文管理蓝图（旧版）
│   └── search_routes.py       #   检索蓝图（旧版）
├── services/                  # 核心业务逻辑
│   ├── search/                # ⭐ 检索服务（核心模块）
│   ├── review/                # ⭐ 综述生成 + LLM 客户端
│   ├── qa/                    # ⭐ RAG 问答（V26.0 新增）
│   ├── ai/                    # AI 服务（旧版，可能被 review/qa 替代）
│   ├── pdf/                   # PDF 标注服务（前端已移除标注，后端保留）
│   ├── query/                 # 旧版检索服务（已被 search/ 替代）
│   ├── l3/                    # （空目录，可能废弃）
│   └── user/                  # （空目录，可能废弃）
├── build_db/                  # 数据库构建脚本
│   ├── parsers/               # ⭐ PDF 解析器（核心模块）
│   ├── build_database.py      # 建库主脚本
│   ├── build_embeddings.py    # 构建向量索引（Chroma）
│   ├── build_fts.py           # 构建 FTS5 全文索引
│   ├── build_paper_graph.py   # 构建论文知识图谱
│   ├── dedup_papers.py        # 论文去重
│   └── ...                    # 其他辅助脚本
├── frontend/                  # 前端页面
│   ├── index.html             # ⭐ 首页（检索页面）
│   ├── qa.html                # ⭐ AI 问答页面（V26.0 新增）
│   ├── review.html            # ⭐ 综述生成 + PDF 阅读页面
│   ├── compare.html           # 双栏对比页面
│   ├── viewer.html            # PDF 查看器（可能废弃）
│   ├── src/                   # 前端 JS/CSS
│   └── vendor/                # 第三方库（pdf.js，已不再使用）
├── scripts/                   # 工具脚本
│   ├── self_check.py          # ⭐ 自检脚本（每次修改后必须运行）
│   ├── tune_retrieval.py      # 检索参数调优脚本
│   └── run_tests.sh           # 测试工作流
├── data/                      # 数据目录（运行时生成）
│   ├── research.db            # SQLite 数据库
│   ├── chroma/                # Chroma 向量索引
│   └── outlines/              # 保存的大纲
├── documents/                 # PDF 源文件
├── csl_styles/                # 参考文献样式
├── docs/                      # 文档
├── VERSION                    # 当前版本号
├── WORKLOG.md                 # ⭐ 开发日志（每次修改必须更新）
├── ARCHITECTURE.md            # ⭐ 本文档（架构总览）
├── README.md                  # 项目说明
├── requirements.txt           # Python 依赖
└── .env.example               # 环境变量示例
```

---

## 三、核心模块详解

### 3.1 检索服务（services/search/）⭐ 核心

| 文件 | 职责 | 状态 |
|------|------|------|
| `unified_retriever.py` | **统一检索入口**，编排所有检索步骤 | ✅ 在用 |
| `hybrid_search.py` | 混合检索（向量 + FTS + RRF 融合） | ✅ 在用 |
| `reranker.py` | Cross-Encoder 重排序（BAAI/bge-reranker-base） | ✅ 在用 |
| `query_router.py` | 查询路由（qa/citation/figure/method/auto） | ✅ 在用 |
| `query_expander.py` | 查询扩展（多查询 + 缩写扩展） | ✅ 在用 |
| `abbreviation_expander.py` | 学术缩写扩展词典（150+ 生物医学缩写） | ✅ 在用 |
| `fts_query_builder.py` | 增强 FTS 查询构建（短语匹配 + NEAR + 实体加权） | ✅ 在用 |
| `mmr_diversifier.py` | MMR 多样性去重（λ=0.6，阈值=0.03） | ✅ 在用 |
| `context_expander.py` | 上下文扩展（小段落→大段落） | ✅ 在用 |
| `chunker.py` | 文本分块（800-token 单位） | ✅ 在用 |
| `graph_traverser.py` | 图谱遍历（CITES/SIMILAR 邻居扩展） | ✅ 在用 |
| `agentic_search.py` | Agentic 多跳搜索 | ✅ 在用 |
| `reference_filter.py` | 参考文献段过滤 | ✅ 在用 |
| `boilerplate_filter.py` | 模板/ boilerplate 过滤 | ✅ 在用 |
| `retrieval_diagnostics.py` | 检索诊断模式 | ✅ 在用 |

**检索流水线**：
```
用户查询 → 查询路由 → 查询扩展（多查询+缩写）→ 向量召回 + FTS召回
→ RRF 融合 → Rerank（保留3倍候选）→ MMR 多样性去重 → 上下文扩展 → 返回结果
```

### 3.2 PDF 解析器（build_db/parsers/）⭐ 核心

| 文件 | 职责 | 状态 |
|------|------|------|
| `parser_orchestrator.py` | **解析编排器**（V3：Docling 主 + GROBID 增强 + 期刊优化） | ✅ 在用 |
| `docling_parser.py` | Docling 解析器（主要解析器） | ✅ 在用 |
| `grobid_parser.py` | GROBID 解析器（元数据 + 参考文献增强，可选） | ✅ 在用 |
| `journal_optimizer.py` | ⭐ **期刊适配**（Nature/Science/Cell 三大期刊家族） | ✅ 在用 |
| `base_parser.py` | 解析器基类 | ✅ 在用 |
| `pdfplumber_parser.py` | pdfplumber 解析器（备用） | ⚠️ 备用 |
| `mineru_parser.py` | MinerU 解析器（备用） | ⚠️ 备用 |

**解析流水线**：
```
PDF → Docling（段落/图表/表格/章节层级）→ GROBID（元数据/参考文献，可选）
→ 期刊感知优化（journal_optimizer）→ 写入数据库
```

### 3.3 综述生成（services/review/）⭐ 核心

| 文件 | 职责 | 状态 |
|------|------|------|
| `llm_client.py` | ⭐ **统一 LLM 客户端**（Ollama 本地 + OpenAI 兼容云端） | ✅ 在用 |
| `review_generator.py` | 综述生成器（大纲 → 证据抽取 → 撰写） | ✅ 在用 |
| `outline_generator.py` | 大纲生成器 | ✅ 在用 |
| `outline_store.py` | 大纲存储（本地文件） | ✅ 在用 |
| `evidence_extractor.py` | 证据抽取器 | ✅ 在用 |
| `conflict_detector.py` | 冲突识别器 | ✅ 在用 |
| `relation_extractor.py` | 关系抽取器 | ✅ 在用 |
| `sentence_locator.py` | 句内定位器 | ✅ 在用 |
| `citation_formatter.py` | 参考文献格式化 | ✅ 在用 |
| `citation_verifier.py` | 引用验证器 | ✅ 在用 |
| `review_store.py` | 综述存储 | ✅ 在用 |
| `models.py` | 数据模型 | ✅ 在用 |

### 3.4 RAG 问答（services/qa/）⭐ V26.0 新增

| 文件 | 职责 | 状态 |
|------|------|------|
| `qa_service.py` | ⭐ **RAG 问答服务**（检索 → 信封 → LLM → 引用解析） | ✅ 在用 |

**问答流水线**：
```
用户问题 → UnifiedRetriever.retrieve（检查是否有结果）
→ UnifiedRetriever.to_envelope（构建编号信封上下文）
→ LLMClient.chat（英文优先，系统提示词强制引用）
→ parse_citations（解析 [P1]/[F2] 等引用 ID）
→ _build_sources（关联到具体论文/段落/图表）
→ 返回答案 + 引用来源 + 检索统计
```

### 3.5 旧版/可能废弃的模块

| 模块 | 说明 | 建议 |
|------|------|------|
| `services/ai/` | 旧版 AI 服务（ai_service.py/envelope_builder.py/rag_validator.py） | 用旧 SearchService + 旧 AI_API_KEY，可能已被 review/qa 替代 |
| `services/query/search_service.py` | 旧版检索服务 | 已被 services/search/ 替代 |
| `routes/` | 旧版蓝图路由 | 主路由已在 api_server.py，蓝图可能未注册 |
| `services/pdf/annotator.py` | PDF 标注服务 | 前端已移除标注功能（V25.14），后端保留但未被调用 |
| `frontend/vendor/pdf.min.js` | PDF.js 库 | V25.14 后改用浏览器原生 iframe，不再使用 |
| `frontend/src/pdf_annotator.js` | PDF 标注前端 | V25.14 后移除标注，可能已废弃 |
| `app.py` | 已删除（2026-10-24） | 与 api_server.py 争 5000 端口；仅注册 3 个 blueprint，review/tasks/abstracts/graph/qa 路由全缺 |
| `services/l3/` | 空目录 | 废弃 |
| `services/user/` | 空目录 | 废弃 |

---

## 三补、核心算法与外部依赖详解

> 本章节详细记录每个模块使用的**算法、关键函数、第三方库/工具**，确保技术选型可追溯。

### 3A.1 检索模块（services/search/）

#### 3A.1.1 向量检索
| 项目 | 详情 |
|------|------|
| **算法** | 稠密向量检索 + 余弦相似度（cosine similarity） |
| **向量库** | **Chroma**（`chromadb.PersistentClient`，本地持久化） |
| **embedding 模型** | **all-mpnet-base-v2**（SentenceTransformers，英文模型，768 维） |
| **关键函数** | `HybridSearch.vector_search()` → `collection.query(query_embeddings, n_results)` |
| **集合** | paragraphs（17397条）、papers（101条）、figures（406条）、tables（119条） |
| **第三方库** | `chromadb`、`sentence-transformers`（内部依赖 `torch`、`transformers`、`huggingface-hub`） |

#### 3A.1.2 FTS 全文检索
| 项目 | 详情 |
|------|------|
| **算法** | SQLite FTS5 倒排索引 + 增强查询构建 |
| **引擎** | **SQLite FTS5**（虚拟表 `paragraphs_fts`、`papers_fts`） |
| **增强查询** | 短语匹配（`"phrase"`）、NEAR 距离（`NEAR(term1 term2, 10)`）、实体词加权（`STAT1^3`） |
| **关键函数** | `FTSQueryBuilder.build()` → 生成增强 FTS 查询；`HybridSearch.fts_search()` → 执行查询 |
| **实体识别** | 正则匹配基因/蛋白符号（大写+数字，如 STAT1、JAK2） |
| **短语检测** | 连字符短语（如 JAK-STAT）、固定学术短语 |
| **第三方库** | `sqlite3`（Python 标准库，FTS5 内置） |

#### 3A.1.3 结果融合（RRF）
| 项目 | 详情 |
|------|------|
| **算法** | **RRF（Reciprocal Rank Fusion，倒数排名融合）** |
| **公式** | `score = Σ weight / (k + rank)`，其中 `k=60`（RRF_K 常量） |
| **动态权重** | V25.19 新增：实体多的查询 FTS 权重 +0.5/实体（上限+1.0），自然语言查询向量权重更高 |
| **关键函数** | `HybridSearch._rrf_fuse(vector_results, fts_results, vector_weight, fts_weight)` |
| **第三方库** | 无（纯 Python 实现） |

#### 3A.1.4 重排序（Rerank）
| 项目 | 详情 |
|------|------|
| **算法** | **Cross-Encoder 交叉编码器重排序** |
| **模型** | **BAAI/bge-reranker-base**（SentenceTransformers CrossEncoder） |
| **原理** | 将 (query, passage) 对输入模型，直接输出相关性分数，比双塔模型更准但更慢 |
| **关键函数** | `Reranker.rerank(query, results, top_k)` → `model.predict([(query, text), ...])` |
| **候选池** | V25.22 修复：rerank 保留 3 倍候选（如 top_k=10 则保留 30 段），供 MMR 多样性选择 |
| **第三方库** | `sentence-transformers`（CrossEncoder） |

#### 3A.1.5 多样性去重（MMR）
| 项目 | 详情 |
|------|------|
| **算法** | **MMR（Maximal Marginal Relevance，最大边际相关性）** |
| **公式** | `MMR_score = λ * relevance - (1-λ) * max_similarity_to_selected` |
| **参数** | `λ=0.6`（MMR_LAMBDA，相关性-多样性平衡）、`min_similarity=0.03`（相似度阈值）、`paper_penalty=0.1`（跨论文奖励） |
| **相似度计算** | **Jaccard 相似度**（`|A∩B| / |A∪B|`），基于分词后的词集合，过滤 150+ 停用词 |
| **关键函数** | `MMRDiversifier.diversify(candidates, top_k, score_key)` → 贪心选择，每次选 MMR 分数最高的 |
| **辅助函数** | `_tokenize(text)` → 分词+停用词过滤；`_jaccard_similarity(set_a, set_b)` → Jaccard 计算 |
| **第三方库** | 无（纯 Python 实现） |

#### 3A.1.6 查询路由
| 项目 | 详情 |
|------|------|
| **算法** | 基于规则的查询分类（非机器学习） |
| **分类类型** | `qa`（问答）、`citation`（引用查找）、`figure`（图表查找）、`method`（方法查找）、`auto`（自动） |
| **规则** | 关键词匹配（如"figure/table"→figure，"cite/reference"→citation） |
| **关键函数** | `QueryRouter.route(query)` → 返回分类结果和推荐检索通道 |
| **第三方库** | 无（纯 Python 规则匹配） |

#### 3A.1.7 查询扩展
| 项目 | 详情 |
|------|------|
| **算法** | 多查询生成 + 学术缩写扩展 |
| **多查询** | 生成多个变体查询（同义改写、关键词提取），分别检索后融合 |
| **缩写扩展** | 150+ 生物医学缩写词典（如 STAT→Signal Transducer and Activator of Transcription），扩展后同时检索原文和扩展词 |
| **关键函数** | `QueryExpander.expand(query)` → 生成查询变体列表；`AbbreviationExpander.expand(query)` → 缩写扩展 |
| **第三方库** | 无（纯 Python + 内置词典） |

#### 3A.1.8 上下文扩展
| 项目 | 详情 |
|------|------|
| **算法** | 小段落→大段落回溯（parent context expansion） |
| **原理** | 检索到的匹配段落可能太短，回溯其父级章节上下文（前后段落），提供更完整的语境 |
| **关键函数** | `ContextExpander.expand(paragraphs, mode, max_parents)` → 为每个段落添加上下文 |
| **标记** | 用 `HIT_START`/`HIT_END` 标记匹配段落在上下文中的位置 |
| **第三方库** | 无（纯 Python 实现） |

#### 3A.1.9 图谱遍历
| 项目 | 详情 |
|------|------|
| **算法** | 基于图的邻居扩展（BFS 思想） |
| **关系类型** | `cites`（引用）、`similar`（语义相似）、`same_author`、`same_topic` |
| **原理** | 从向量检索到的种子论文出发，沿 cross_paper_index 中的边扩展，找到向量检索可能遗漏的相关论文 |
| **关键函数** | `GraphTraverser.expand(seed_paper_ids, max_neighbors, relation)` → 返回扩展后的邻居论文 |
| **第三方库** | `sqlite3`（查询 cross_paper_index 表） |

#### 3A.1.10 过滤模块
| 模块 | 算法 | 关键函数 |
|------|------|----------|
| **参考文献过滤** | 规则匹配（识别 References/Bibliography 段落） | `reference_filter.is_reference_entry(paragraph)` |
| **Boilerplate 过滤** | 规则匹配（识别期刊模板、声明、版权信息等） | `boilerplate_filter.clean_boilerplate(text)` |

#### 3A.1.11 检索诊断
| 项目 | 详情 |
|------|------|
| **算法** | 分阶段计时 + 结果统计 |
| **记录内容** | 每个阶段（query_router/vector_search/fts_search/rrf_fuse/rerank/mmr_diversify）的耗时、返回数量、分数分布 |
| **关键函数** | `RetrievalDiagnostics.set_result(stage, results, score_key)` → 记录阶段结果；`get_diagnostics_report()` → 生成诊断报告 |
| **第三方库** | `time`（标准库计时） |

---

### 3A.2 PDF 解析模块（build_db/parsers/）

#### 3A.2.1 Docling 解析器（主解析器）
| 项目 | 详情 |
|------|------|
| **工具** | **Docling**（IBM 开源的文档智能解析库） |
| **核心类** | `DocumentConverter`（文档转换器）、`PdfFormatOption`（PDF 格式选项）、`PdfPipelineOptions`（流水线选项） |
| **分块器** | `HierarchicalChunker`（层级分块，基于文档结构树） |
| **解析内容** | 段落、章节层级（level1/2/3）、图表、表格、页码、边界框（bbox） |
| **关键函数** | `DoclingParser.parse(pdf_path, paper_id)` → `DocumentConverter.convert(pdf_path)` → 遍历文档结构树提取内容 |
| **第三方库** | `docling`、`docling-core`（内部依赖 `pymupdf`、`pillow`、`pytesseract`（OCR，可选）） |

#### 3A.2.2 GROBID 解析器（增强，可选）
| 项目 | 详情 |
|------|------|
| **工具** | **GROBID**（GeneRation Of BIbliographic Data，机器学习的文献元数据/参考文献解析服务） |
| **部署方式** | Docker 容器（`grobid/grobid:0.9.1-full`，端口 8070） |
| **调用方式** | REST API（`requests.post`，上传 PDF，返回 TEI XML） |
| **解析内容** | 标题、作者、机构、期刊、年份、DOI、结构化参考文献（含每条参考文献的 DOI/标题/作者/期刊/年份） |
| **关键函数** | `GrobidParser.parse(pdf_path, paper_id)` → 调用 `/api/processFulltextDocument` → 解析 TEI XML（`xml.etree.ElementTree`） |
| **可用性检测** | `GrobidParser.is_alive()` → 请求 `/api/isalive` |
| **第三方库** | `requests`、`xml.etree.ElementTree`（标准库） |

#### 3A.2.3 期刊优化器（journal_optimizer.py）
| 项目 | 详情 |
|------|------|
| **算法** | 基于规则的期刊家族检测 + 针对性优化 |
| **期刊家族** | Nature（30+ 子刊）、Science（7 个子刊）、Cell（10+ 子刊）、Other（通用） |
| **检测方式** | DOI 前缀匹配（如 `10.1038/s41586`→Nature，`10.1126/science`→Science，`10.1016/j.cell`→Cell） |
| **优化内容** | 期刊特有的章节标题识别、卷/期/页码提取、章节类型规范化、双栏布局提示 |
| **关键函数** | `optimize_for_journal(result)` → 检测期刊家族 → 应用对应优化规则 |
| **第三方库** | `re`（标准库正则匹配） |

#### 3A.2.4 标题合理性检查
| 项目 | 详情 |
|------|------|
| **算法** | 基于规则的异常标题检测 |
| **检测规则** | ①全大写（大写字母比例>85%，可能是 running header）②consortium/study group 后缀 ③截断（以 ( 或 - 结尾）④过短（<10 字符） |
| **关键函数** | `is_grobid_title_suspicious(title)` → 返回 (is_suspicious, reason) |
| **用途** | 防止 GROBID 把 running header 或 consortium 名误判为论文标题 |

#### 3A.2.5 备用解析器
| 解析器 | 工具 | 状态 |
|--------|------|------|
| `pdfplumber_parser.py` | **pdfplumber**（基于 pdfminer 的 PDF 解析） | ⚠️ 备用，当前未使用 |
| `mineru_parser.py` | **MinerU**（上海人工智能实验室开源的 PDF 解析） | ⚠️ 备用，当前未使用 |
| `base_parser.py` | 解析器抽象基类（ABC） | ✅ 基类，所有解析器继承 |

---

### 3A.3 LLM 与综述模块（services/review/）

#### 3A.3.1 统一 LLM 客户端（llm_client.py）
| 项目 | 详情 |
|------|------|
| **设计** | 统一接口，支持 Ollama（本地）和 OpenAI 兼容 API（云端） |
| **调用方式** | **直接用 `requests.post` 调用 REST API**（不依赖 openai Python 库） |
| **Ollama 模式** | 请求 `{host}/api/chat`，请求体 `{model, messages, stream, options}` |
| **OpenAI 兼容模式** | 请求 `{base_url}/chat/completions`，请求体 `{model, messages, temperature, max_tokens}`，Header `Authorization: Bearer {api_key}` |
| **关键函数** | `LLMClient.chat(system_prompt, user_prompt, temperature)` → 构建 payload → `requests.post` → 解析响应 → 返回文本 |
| **辅助函数** | `is_available()`（检测服务可用性，带缓存）、`list_models()`（列出可用模型） |
| **重试机制** | 最多 `max_retries=3` 次，重试间隔 `retry_delay * attempt` 秒递增 |
| **超时** | `timeout=120` 秒 |
| **第三方库** | `requests`、`time`、`os`（标准库） |

#### 3A.3.2 综述生成器（review_generator.py）
| 项目 | 详情 |
|------|------|
| **流水线** | 大纲生成 → 证据抽取 → 冲突识别 → 句内定位 → 撰写 → 引用格式化 |
| **大纲生成** | LLM 根据检索结果生成综述大纲（`outline_generator.py`） |
| **证据抽取** | 从检索结果中抽取与大纲每个小节相关的证据（`evidence_extractor.py`） |
| **冲突识别** | 识别不同文献之间的矛盾观点（`conflict_detector.py`），标记"伪争议"（V25.5 优化） |
| **关系抽取** | 抽取文献间的引用/支持/反对关系（`relation_extractor.py`） |
| **句内定位** | 将 LLM 生成的句子定位到原始文献段落（`sentence_locator.py`） |
| **引用格式化** | 按 CSL 样式格式化参考文献（`citation_formatter.py`），支持多种期刊样式 |
| **引用验证** | 验证生成的引用是否真实存在于文献库（`citation_verifier.py`） |
| **存储** | 综述和大纲本地存储（`review_store.py`、`outline_store.py`） |
| **第三方库** | `sqlite3`、`json`、`os`、`collections.defaultdict` |

---

### 3A.4 RAG 问答模块（services/qa/）

#### 3A.4.1 问答服务（qa_service.py）
| 步骤 | 算法/工具 | 关键函数 |
|------|-----------|----------|
| **1. 检索** | UnifiedRetriever（向量+FTS+RRF+Rerank+MMR，见 3A.1） | `retriever.retrieve(query, paper_id, top_paragraphs, top_figures)` |
| **2. 上下文构建** | 编号信封格式（[P1]/[F2]/[R3] 稳定 ID） | `retriever.to_envelope(query, ...)` → 内部调用 retrieve 后格式化 |
| **3. LLM 生成** | LLMClient（见 3A.3.1），英文优先，系统提示词强制引用 | `llm.chat(system_prompt, user_prompt, temperature=0.3)` |
| **4. 引用解析** | 正则表达式匹配 `[PTFRCG数字]` 格式 | `parse_citations(answer)` → `re.findall(r'\[(P|F|T|R|C|G)(\d+)\]', answer)` |
| **5. 来源关联** | 根据引用 ID 映射到 retrieve 结果中的对应段落/图表/论文 | `_build_sources(retrieval_result, citations)` |
| **6. 无结果处理** | 检索结果为空时直接返回提示，不调用 LLM | `total_hits == 0` 判断 |

**系统提示词要点**（英文）：
1. 只使用证据中的信息，不编造
2. 每个事实陈述必须标注引用（[P1]、[F2] 等）
3. 证据不足时明确说明，不猜测
4. 默认用英文回答（与文献语言一致，准确性最高）
5. 优先引用段落 [P]，其次图表 [F]/[T]，最后相关论文 [R]

**第三方库**：`re`（标准库正则）、`os`（环境变量）

---

### 3A.5 知识图谱模块

#### 3A.5.1 图谱构建（build_db/build_paper_graph.py）
| 项目 | 详情 |
|------|------|
| **CITES 边** | DOI 匹配 + 标题模糊匹配，从 citations 表中识别论文间引用关系 |
| **SIMILAR 边** | 基于论文摘要的 cosine 相似度（Chroma 向量），阈值 >0.5 |
| **去自环** | 排除 source_paper_id == target_paper_id 的自引用 |
| **关键函数** | `build_paper_graph.py --apply` → 扫描 citations → DOI/标题匹配 → 计算摘要相似度 → 写入 cross_paper_index |
| **当前数据** | 341 条边（19 CITES + 322 SIMILAR），9 个连通分量，最大分量 52 篇 |

#### 3A.5.2 社区发现（build_db/build_communities.py）
| 项目 | 详情 |
|------|------|
| **算法** | 基于图的社区发现（可能是 Louvain 或标签传播，待确认） |
| **用途** | 将论文按研究主题聚类，用于图谱可视化分组 |
| **API** | `/api/communities` |

---

### 3A.6 前端（frontend/）

| 页面 | 核心技术 | 关键 JS 文件 |
|------|----------|-------------|
| **index.html**（检索） | 原生 HTML + Vanilla JS + Fetch API | 内联 JS |
| **qa.html**（问答，V26.0） | 原生 HTML + Vanilla JS + Fetch API + localStorage（历史记录） | 内联 JS |
| **review.html**（综述+阅读） | 原生 HTML + Vanilla JS + 浏览器原生 iframe（PDF 渲染） | `src/review.js`、`src/outline_editor.js`、`src/outline_core.js`、`src/pdf_viewer.js`、`src/paper_list.js`、`src/resizer.js`、`src/paper_importer.js`、`src/supplementary_manager.js` |
| **compare.html**（双栏对比） | 原生 HTML + Vanilla JS | 内联 JS |

**前端设计原则**：
- 不使用框架（Vue/React），纯 Vanilla JS，轻量无构建步骤
- PDF 渲染用浏览器原生 iframe（V25.14 后替代 PDF.js），不依赖第三方 PDF 库
- 样式用内联 CSS + CSS 变量，不使用 CSS 框架
- 拖拽调宽用原生鼠标事件（`mousedown`/`mousemove`/`mouseup`），不依赖拖拽库
- 数据存储用 `localStorage`（问答历史、布局偏好），不依赖前端数据库

---

### 3A.7 第三方依赖完整清单

#### 3A.7.1 requirements.txt 中声明的依赖
| 库 | 版本 | 用途 | 使用模块 |
|----|------|------|----------|
| **Flask** | 2.3.3 | Web 框架 | api_server.py |
| **flask-cors** | 4.0.0 | 跨域支持 | api_server.py |
| **sqlite-utils** | 3.35.1 | SQLite 工具 | build_db/ |
| **openai** | 1.14.0 | OpenAI API 客户端 | ⚠️ 可能未使用（llm_client.py 用 requests 直接调用） |
| **python-dotenv** | 1.0.1 | 环境变量加载 | config/settings.py |
| **tqdm** | 4.66.2 | 进度条 | build_db/ |

#### 3A.7.2 未在 requirements.txt 但实际使用的依赖（需补充）
| 库 | 用途 | 使用模块 |
|----|------|----------|
| **chromadb** | 向量数据库 | services/search/hybrid_search.py、build_db/build_embeddings.py |
| **sentence-transformers** | embedding + CrossEncoder 重排序 | services/search/hybrid_search.py、services/search/reranker.py、build_db/build_embeddings.py |
| **docling** | PDF 智能解析 | build_db/parsers/docling_parser.py |
| **docling-core** | Docling 核心类型 | build_db/parsers/docling_parser.py |
| **requests** | HTTP 请求（LLM API、GROBID API） | services/review/llm_client.py、build_db/parsers/grobid_parser.py |
| **pymupdf** | PDF 处理（备用解析器 + DOI 提取） | build_db/parsers/pdfplumber_parser.py（备用）、fetch_metadata.py |

#### 3A.7.3 Python 标准库（无需安装）
| 库 | 用途 |
|----|------|
| `sqlite3` | SQLite 数据库 |
| `re` | 正则表达式（引用解析、实体识别、标题检查） |
| `os` / `sys` / `pathlib` | 文件路径、环境变量 |
| `json` | JSON 序列化 |
| `time` | 计时、重试延迟 |
| `hashlib` | 生成 paper_id（MD5） |
| `collections`（deque, defaultdict, OrderedDict） | 数据结构 |
| `typing` | 类型注解 |
| `abc` | 抽象基类（解析器基类） |
| `xml.etree.ElementTree` | 解析 GROBID 返回的 TEI XML |

#### 3A.7.4 外部服务/工具（需单独部署/配置/联网）

| 服务/工具 | 用途 | 部署/配置方式 | 使用模块 | 状态 |
|-----------|------|--------------|----------|------|
| **Ollama** | 本地 LLM 推理 | `ollama serve` + `ollama pull qwen2.5:14b` | services/review/llm_client.py | 可选（二选一） |
| **DeepSeek API** | 云端 LLM 推理 | API Key 配置 | services/review/llm_client.py | 可选（二选一） |
| **GROBID** | 文献元数据/参考文献解析 | Docker `grobid/grobid:0.9.1-full`，端口 8070 | build_db/parsers/grobid_parser.py | 可选（未启动时 Docling 独立工作） |
| **HuggingFace 模型缓存** | embedding/rerank 模型 | 本地缓存（`TRANSFORMERS_OFFLINE=1`） | services/search/、build_db/build_embeddings.py | 必需（已下载） |
| **Zotero** | 文献管理，元数据导入 | Zotero 客户端 + 导出文件（CSV/JSON/CSL） | import_zotero_metadata.py | 可选（用于批量导入已有文献库） |
| **NCBI** | 生物医学文献元数据获取 | 联网 API（E-utilities） | fetch_from_ncbi.py | 可选（用于补充论文元数据） |
| **Crossref API** | DOI 解析/元数据获取 | 联网 API（`api.crossref.org`） | fetch_metadata.py、resolve_ref_dois.py | 可选（用于解析 DOI 获取元数据） |
| **DOI.org** | DOI 解析/重定向 | 联网（`doi.org`） | fetch_metadata.py | 可选（用于解析 DOI 链接） |

**模型清单**（HuggingFace 托管，本地缓存）：
| 模型 | 用途 | 大小 |
|------|------|------|
| `all-mpnet-base-v2` | 文本 embedding（768 维，英文） | ~0.4GB |
| `BAAI/bge-reranker-base` | Cross-Encoder 重排序 | ~1.1GB |
| `qwen2.5:14b`（Ollama） | 本地 LLM 生成 | ~9GB |

#### 3A.7.5 Zotero 元数据导入详细说明（V25.18）

> **脚本**：`import_zotero_metadata.py`
> **用途**：从 Zotero 导出的文献库中提取元数据，批量补全/更新 Sci-Pal papers 表的元数据（特别是 abstract 摘要、作者、期刊等）。

**工作原理**：
- ❌ **不直接读 Zotero 的数据库文件**（zotero.sqlite）
- ✅ **读 Zotero 导出的 CSL JSON 文件**（标准文献交换格式）

**使用流程**：
```
1. 打开 Zotero 客户端
2. 选中要导入的文献（可全选）
3. 右键 → 导出条目 → 格式选 "CSL JSON" → 保存为 zotero_export.json
4. 运行导入脚本：
   python3 import_zotero_metadata.py zotero_export.json data/research.db
```

**匹配策略**（按优先级）：
1. **DOI 精确匹配**（最准确）：归一化 DOI（去掉 `https://doi.org/` 前缀、转小写）后精确匹配
2. **标题模糊匹配**（兜底）：标题归一化（去 HTML 标签、去标点、转小写）后匹配
3. 都匹配不上 → 跳过，记录为未匹配

**CSL JSON 字段 → Sci-Pal 字段映射**：
| CSL JSON 字段 | Sci-Pal papers 字段 | 说明 |
|---------------|---------------------|------|
| `title` | `title` | 标题（始终用 Zotero 的，更规范） |
| `author[]`（family+given） | `authors` | 作者，格式化为 "Family Given; Family Given" |
| `container-title` | `journal` | 期刊名 |
| `DOI` | `doi` | DOI（归一化后） |
| `issued.date-parts[0][0]` | `year` | 年份 |
| `volume` | `volume` | 卷 |
| `issue` | `issue` | 期 |
| `page` | `pages` | 页码 |
| `abstract` | `abstract` | 摘要（重点补全字段） |
| `publisher` | `publisher` | 出版商 |
| `language` | `language` | 语言 |
| `type` | `paper_type` | 类型映射：article-journal→J, book→B, chapter→C, thesis→T, report→R |
| `keyword` | `keywords` | 关键词 |
| - | `parse_engine` | 标记为 `zotero_import` |
| - | `updated_at` | 更新时间戳 |

**关键函数**：
- `normalize_title(title)` — 标题归一化（去 HTML、去标点、转小写）
- `normalize_doi(doi)` — DOI 归一化（去 URL 前缀、转小写）
- `format_authors(authors_list)` — CSL 作者数组 → 分号分隔字符串
- `extract_year(issued)` — 从 CSL issued 字段提取年份
- `clean_text(text)` — 清理 HTML 标签和多余空白
- `import_zotero_metadata(json_path, db_path)` — 主函数

**输出统计**：
- Zotero 文献总数、DOI 匹配数、标题匹配数、未匹配数
- 各字段更新计数
- abstract 填充数（重点关注）
- 未匹配文献列表（最多显示 20 条）
- 更新后 abstract 填充率验证

---

### 3A.8 关键算法速查表

| 算法 | 用途 | 模块 | 核心参数 |
|------|------|------|----------|
| **余弦相似度** | 向量检索相似度 | hybrid_search.py | Chroma 内置 |
| **RRF（倒数排名融合）** | 向量+FTS 结果融合 | hybrid_search.py | k=60, 动态权重 |
| **Cross-Encoder** | 重排序 | reranker.py | BAAI/bge-reranker-base |
| **MMR（最大边际相关性）** | 多样性去重 | mmr_diversifier.py | λ=0.6, min_sim=0.03 |
| **Jaccard 相似度** | MMR 中文本相似度计算 | mmr_diversifier.py | 分词+停用词过滤 |
| **FTS5 倒排索引** | 全文检索 | SQLite 内置 | 短语匹配+NEAR+加权 |
| **BFS（广度优先）** | 图谱邻居扩展 | graph_traverser.py | max_neighbors |
| **正则表达式** | 引用解析、实体识别、标题检查 | 多模块 | 多种模式 |
| **层级分块** | PDF 段落分块 | docling HierarchicalChunker | 基于文档结构树 |
| **TEI XML 解析** | GROBID 结果解析 | grobid_parser.py | xml.etree.ElementTree |

---

## 四、API 路由清单

> 所有路由定义在 `api_server.py` 中。`routes/` 目录下的蓝图可能未注册（待确认）。

### 4.1 系统
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |

### 4.2 检索
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/retrieve` | GET/POST | ⭐ 统一检索（向量+FTS+RRF+Rerank+MMR） |
| `/api/agentic/search` | GET/POST | Agentic 多跳搜索 |

### 4.3 RAG 问答（V26.0 新增）
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/qa/ask` | POST | ⭐ 提问（参数：question, paper_id, diagnostics） |
| `/api/qa/status` | GET | ⭐ LLM 状态检查（提供商/模型/可用性） |

### 4.4 论文管理
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/papers` | GET | 论文列表 |
| `/api/papers/<paper_id>` | GET | 论文详情 |
| `/api/papers/local` | GET | 本地文献库浏览（V25.11） |
| `/api/papers/parse` | POST | 按需触发解析（V25.14） |
| `/api/papers/import` | POST | 导入论文 |
| `/api/papers/<paper_id>/pdf` | GET | PDF 文件（浏览器原生渲染） |
| `/api/papers/<paper_id>/graph` | GET | 单篇论文的图谱关系 |
| `/api/papers/<paper_id>/annotate` | POST | PDF 标注（前端已移除，后端保留） |
| `/api/papers/<paper_id>/annotations` | GET | 标注列表（前端已移除） |

### 4.5 补充材料
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/papers/<paper_id>/supplementary` | GET/POST | 补充材料列表/上传 |
| `/api/papers/<paper_id>/supplementary/<supp_id>/download` | GET | 下载补充材料 |
| `/api/papers/<paper_id>/supplementary/<supp_id>` | DELETE | 删除补充材料 |
| `/api/papers/<paper_id>/supplementary/link` | POST | 关联补充材料 |

### 4.6 知识图谱
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/graph/stats` | GET | 图谱统计 |
| `/api/communities` | GET | 社区发现（论文聚类） |

### 4.7 综述生成
| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/review/outline` | GET/POST | 生成/获取大纲 |
| `/api/review/outline/saved` | GET | 已保存大纲列表 |
| `/api/review/outline/saved/<name>` | GET | 加载指定大纲 |
| `/api/review/outline/save` | POST | 保存大纲 |
| `/api/review/outline/saved/<name>` | DELETE | 删除大纲 |
| `/api/review/generate` | GET/POST | 生成综述 |
| `/api/review/<review_id>` | GET | 综述详情 |
| `/api/review/<review_id>/sentence/<sentence_id>` | GET | 句子定位 |
| `/api/review/llm_status` | GET | LLM 状态（综述模块用） |

### 4.8 前端页面
| 路由 | 说明 |
|------|------|
| `/` | 首页（检索页面 index.html） |
| `/qa.html` | ⭐ AI 问答页面（V26.0 新增） |
| `/review.html` | 综述生成 + PDF 阅读页面 |
| `/compare.html` | 双栏对比页面 |

---

## 五、数据库表结构

> 数据库文件：`data/research.db`（SQLite）
> 向量索引：`data/chroma/`（Chroma，独立于 SQLite）

### 5.1 主表

#### papers（论文元数据）
| 字段 | 类型 | 说明 |
|------|------|------|
| paper_id | TEXT PK | 论文 ID |
| filename | TEXT | PDF 文件名 |
| title | TEXT | 标题 |
| authors | TEXT | 作者（JSON 或逗号分隔） |
| abstract | TEXT | 摘要 |
| journal | TEXT | 期刊 |
| year | INTEGER | 年份 |
| doi | TEXT | DOI |
| keywords | TEXT | 关键词 |
| volume/issue/pages | TEXT | 卷/期/页码 |
| paper_type | TEXT | 论文类型（默认 'J'） |
| publisher | TEXT | 出版商 |
| language | TEXT | 语言（默认 'en'） |
| affiliations/funding | TEXT | 机构/基金 |
| parse_status | TEXT | 解析状态（默认 'completed'） |
| parse_engine | TEXT | 解析引擎 |
| total_paragraphs/figures/tables/citations | INTEGER | 统计计数 |
| created_at/updated_at | TEXT | 创建/更新时间 |

#### paragraphs（段落）
| 字段 | 类型 | 说明 |
|------|------|------|
| para_id | TEXT PK | 段落 ID |
| paper_id | TEXT FK | 所属论文 |
| section_level1/2/3 | TEXT | 章节层级 |
| text | TEXT | 段落文本 |
| sequence | INTEGER | 顺序号 |
| page | INTEGER | 页码 |
| bbox | TEXT | 边界框坐标 |

#### figures（图表）
| 字段 | 类型 | 说明 |
|------|------|------|
| fig_id | TEXT PK | 图表 ID |
| paper_id | TEXT FK | 所属论文 |
| fig_number | TEXT | 图号 |
| caption | TEXT | 图注 |
| file_path | TEXT | 图片文件路径 |
| page | INTEGER | 页码 |
| bbox | TEXT | 边界框 |

#### tables（表格）
| 字段 | 类型 | 说明 |
|------|------|------|
| table_id | TEXT PK | 表格 ID |
| paper_id | TEXT FK | 所属论文 |
| table_number | TEXT | 表号 |
| caption | TEXT | 表注 |
| markdown | TEXT | 表格内容（Markdown 格式） |
| page | INTEGER | 页码 |

#### citations（参考文献）
| 字段 | 类型 | 说明 |
|------|------|------|
| citation_id | TEXT PK | 引用 ID |
| paper_id | TEXT FK | 所属论文 |
| ref_number | TEXT | 引用编号 |
| raw_text | TEXT | 原始文本 |
| doi | TEXT | DOI |
| title/authors/journal/year | - | 解析出的元数据 |

#### supplementary_files（补充材料，V25.17 新增）
| 字段 | 类型 | 说明 |
|------|------|------|
| supp_id | TEXT PK | 补充材料 ID |
| paper_id | TEXT FK | 所属论文 |
| filename | TEXT | 文件名 |
| file_type | TEXT | 文件类型 |
| file_path | TEXT | 文件路径 |
| file_size | INTEGER | 文件大小 |
| description | TEXT | 描述 |
| created_at | TEXT | 创建时间 |

### 5.2 索引表

#### paper_index（论文内索引）
段落 ↔ 图表、段落 ↔ 表格、段落 ↔ 引用之间的关联关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| index_id | TEXT PK | 索引 ID |
| paper_id | TEXT FK | 所属论文 |
| source_type/source_id | TEXT | 源类型/ID（paragraph/figure/table/citation） |
| target_type/target_id | TEXT | 目标类型/ID |
| relation | TEXT | 关系（mentions/cites/contains） |

#### cross_paper_index（跨论文索引）⭐ 知识图谱
论文之间的引用关系和相似关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| link_id | TEXT PK | 关系 ID |
| source_paper_id | TEXT FK | 源论文 |
| target_paper_id | TEXT FK | 目标论文 |
| relation | TEXT | 关系（cites/similar/same_author/same_topic） |
| confidence | REAL | 置信度（默认 1.0） |

**当前数据**：341 条边（19 CITES + 322 SIMILAR），9 个连通分量，最大分量 52 篇论文。

### 5.3 FTS 全文索引（虚拟表）
- `paragraphs_fts`：段落全文索引（FTS5）
- `papers_fts`：论文全文索引（FTS5）

### 5.4 Chroma 向量索引（独立存储）
- `paragraphs` 集合：17397 条段落向量
- `papers` 集合：101 条论文摘要向量
- `figures` 集合：406 条图表向量
- `tables` 集合：119 条表格向量

**embedding 模型**：`all-mpnet-base-v2`（英文模型）
**rerank 模型**：`BAAI/bge-reranker-base`

---

## 六、已完成功能清单（按模块）

### 6.1 文献解析
- ✅ Docling 主要解析器（段落/图表/表格/章节层级）
- ✅ GROBID 增强（元数据 + 结构化参考文献，可选）
- ✅ 期刊适配（Nature/Science/Cell 三大期刊家族，V25.16）
- ✅ 标题合理性检查（防止 running header/consortium 名）
- ✅ DOI 提取与期刊推断
- ✅ 图片提取与导出
- ✅ 批量解析

### 6.2 数据治理
- ✅ 论文去重（192→101 篇，删除 91 篇重复）
- ✅ 向量索引全量重建（17397 条）
- ✅ FTS 索引重建
- ✅ 知识图谱重建（341 条边）
- ✅ 空壳 PDF 检测（6 个 8-10 字节文件）
- ✅ abstract 填充率监控（93/101，8 篇缺失）

### 6.3 检索优化（V25.19-V25.23）
- ✅ 增强 FTS 查询（短语匹配 + NEAR 距离 + 实体词加权）
- ✅ 动态 RRF 权重（根据查询类型自动调整向量/FTS 权重）
- ✅ MMR 多样性去重（λ=0.6，阈值=0.03，跨论文奖励=0.1）
- ✅ 检索诊断模式
- ✅ 学术缩写扩展词典（150+ 生物医学缩写）
- ✅ Rerank 候选池扩大（3 倍候选，MMR 真正生效）
- ✅ 参数调优脚本（tune_retrieval.py）

### 6.4 RAG 问答（V26.0-V26.2）
- ✅ 问答服务（检索 → 信封 → LLM → 引用解析）
- ✅ 英文优先（系统提示词 + 快捷问题 + 界面说明）
- ✅ 引用溯源（[P1]/[F2]/[R3]，点击跳转来源）
- ✅ LLM 多提供商支持（Ollama 本地 + DeepSeek + OpenAI 兼容）
- ✅ 前端问答页面（LLM 状态 + 快捷问题 + 历史记录）
- ✅ 首页导航入口

### 6.5 知识图谱
- ✅ 论文图谱构建（CITES + SIMILAR 关系）
- ✅ 图谱遍历（邻居扩展）
- ✅ 社区发现（论文聚类）
- ✅ 图谱统计 API
- ❌ 前端可视化（待做，V27.0）

### 6.6 综述生成
- ✅ 大纲生成（LLM 生成）
- ✅ 大纲可视化编辑器（三栏布局）
- ✅ 证据抽取
- ✅ 冲突识别
- ✅ 句内定位
- ✅ 参考文献格式化
- ✅ 综述预览页面
- ✅ 双 Provider 架构（本地 Ollama + 云端 API）

### 6.7 PDF 阅读
- ✅ 浏览器原生 iframe 渲染（V25.14，替代 PDF.js）
- ✅ 三栏布局（大纲/论文/段落）
- ✅ 拖拽调宽（resizer.js）
- ✅ 左右栏互换
- ✅ 未解析文献按需触发解析
- ✅ 本地文献库浏览

### 6.8 其他
- ✅ 补充材料管理
- ✅ 双栏对比页面
- ✅ 自检脚本（self_check.py，100+ 检查项）
- ✅ 部署脚本（deploy_v25.11~v25.14.sh）

---

## 七、待办事项（接下来要做什么）

### 高优先级（用户已明确要求）
1. **知识图谱可视化**（V27.0）
   - 前端展示 cross_paper_index 的 341 条关系
   - 支持点击节点查看论文详情
   - 拖拽布局、按社区分组高亮
   - 推荐库：ECharts graph 或 vis.js

2. **文献管理**（V28.0）
   - 标签、收藏夹、文件夹
   - 阅读进度记录
   - 需要新增数据库表（tags/favorites/folders/reading_progress）

3. **阅读统计**（V29.0）
   - 读了多少篇、花了多少时间
   - 关注哪些领域/期刊
   - 需要新增数据库表（reading_stats/reading_history）

### 中优先级（检索优化 V2 阶段，用户说放到后面）
- 动态调整 λ（根据查询类型/结果分布）
- 基于论文质量的重排序（期刊影响因子/引用数）
- 查询改写（LLM 优化查询表述）
- **句子级切分与单向索引**（用户确认要做，不紧急）：每个大段落下面按句子切开，标上序号，放在大段下面；单向索引（大段→句子，句子不反向关联大段）；引用精度从段落级 [P1] 提升到句子级 [P1-S2]；待讨论切分规则和存储设计

### 低优先级（远期规划）
- 句子级独立向量索引（论文量 500+ 时再考虑）
- 指代消解（Contextual Retrieval）
- 语义切分（Semantic Chunking）
- CLIP 图片内容向量检索
- 图表自动插入综述
- Cytoscape.js 研究脉络/观点冲突图谱

---

## 八、已放弃/暂缓的功能（为什么放弃）

| 功能 | 状态 | 放弃原因 | 重新评估条件 |
|------|------|---------|------------|
| **PDF 标注/笔记** | ❌ 已放弃（V25.14） | 显示效果太差，PDF.js 渲染模糊，标注定位不准；转用浏览器原生 iframe 渲染后无法叠加标注 | 如果浏览器原生 PDF 支持 JS 标注 API，或找到更好的标注方案 |
| **NLI/LoRA/微调** | ⏸️ 暂缓 | RAG 系统瓶颈通常在检索不在生成；微调成本高、需要标注数据 | 检索优化到顶后，生成质量仍不满足需求时 |
| **句子级独立向量库** | ⏸️ 暂缓 | 101 篇论文约 8-13 万句，Chroma 体积翻 5-8 倍；用"段落检索+句内定位"替代 | 论文量 ≥500 篇，或句内定位准确率不足 |
| **指代消解** | ⏸️ 暂缓 | 每篇论文过一遍 LLM 需 1-2 小时，成本高；段落回溯可消解大部分指代 | 综述 Agent 跑通后，发现 It/This 导致的理解错误是主要痛点 |
| **句子级关系图谱** | ⏸️ 暂缓 | 句子级关系抽取准确率不高，O(n²)比较量大；先做段落级 | 段落级关系跑通且准确率验证后 |
| **BGE-M3 替换 all-mpnet-base-v2** | ⏸️ 暂缓 | 换模型要重建全部索引；mpnet 在英文文献上效果足够 | 中文文献占比 >30%，或多模态统一 embedding 需求 |
| **Vue3 替换 Vanilla JS 前端** | ⏸️ 暂缓 | 当前前端够用 | 前端交互复杂度大幅提升（如图谱可视化编辑器） |
| **LanceDB 替换 Chroma** | ⏸️ 暂缓 | 101 篇论文 Chroma 完全够 | 论文量 ≥1000 篇，或需要服务端部署 |

> **NLI/LoRA/微调 — 补充说明（V33.14 更新）**
>
> #### NLI 接回触发条件（满足任一即启动）
> 1. 正则引用覆盖率校验接入后，用户实测仍出现"引用 ID 都标了但答案与证据语义矛盾"的案例，且每周 ≥3 例
> 2. 检索侧（混合检索/重排/图谱扩展/在线搜索）迭代到 V35 之后，检索准确率 ≥90% 但用户满意度仍卡在生成质量
> 3. 出现可复用的轻量 NLI 模型（≤500MB，单句推理 <100ms），且 8GB 显存预算允许
>
> #### NLI 接入方案预告（到时再实施）
> - **模型选型**：bge-reranker 或 DeBERTa-v3-mnli 类 cross-encoder
> - **接入位置**：`QAService.ask()` 中，`RAGValidator` 正则覆盖率校验通过之后
> - **策略**：对答案逐句做 entailment 判定；contradiction 的句子删除或标 `[UNVERIFIED]`；neutral 的句子降级为"无直接证据"
> - **非阻塞**：NLI 校验作为后处理，不通过时标 warning，不触发重检索

---

## 九、环境变量配置

### 9.1 必需配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TRANSFORMERS_OFFLINE` | - | **必须设为 1**，禁止联网下载模型 |
| `HF_HUB_OFFLINE` | - | **必须设为 1**，禁止 HuggingFace 联网 |

### 9.2 LLM 配置（二选一）

**方式 A：本地 Ollama**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCIPAL_LLM_PROVIDER` | `ollama` | 提供商（ollama/openai） |
| `SCIPAL_LLM_HOST` | `http://localhost:11434` | Ollama 服务地址 |
| `SCIPAL_LLM_MODEL` | `qwen2.5:14b` | 模型名 |
| `SCIPAL_LLM_LIGHT_MODEL` | `qwen2.5:7b` | 轻量模型名 |

**方式 B：OpenAI 兼容云端（DeepSeek/DashScope/OpenAI）**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCIPAL_LLM_PROVIDER` | `openai` | 提供商 |
| `SCIPAL_LLM_BASE_URL` | - | API 地址（DeepSeek: `https://api.deepseek.com/v1`） |
| `SCIPAL_LLM_API_KEY` | - | API Key |
| `SCIPAL_LLM_MODEL` | `qwen-plus` | 模型名（DeepSeek: `deepseek-chat`） |
| `SCIPAL_LLM_LIGHT_MODEL` | `qwen-turbo` | 轻量模型名 |

**LLM 可选配置**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCIPAL_LLM_TIMEOUT` | `120` | 请求超时（秒） |
| `SCIPAL_LLM_MAX_RETRIES` | `3` | 最大重试次数 |
| `SCIPAL_LLM_TEMPERATURE` | `0.3` | 生成温度 |

### 9.3 旧版配置（可能已废弃）
| 变量 | 说明 | 状态 |
|------|------|------|
| `AI_API_KEY` | 旧版 AI 服务用 | ⚠️ 可能已被 SCIPAL_LLM_API_KEY 替代 |
| `AI_MODEL` | 旧版模型名 | ⚠️ 可能已废弃 |
| `AI_BASE_URL` | 旧版 API 地址 | ⚠️ 可能已废弃 |

### 9.4 服务配置
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCIPAL_HOST` | `0.0.0.0` | 监听地址 |
| `SCIPAL_PORT` | `5000` | 监听端口 |
| `SCIPAL_DEBUG` | `False` | 调试模式 |

---

## 十、启动流程

### 10.1 前置条件
- Python 3.10+
- 虚拟环境（venv_sciPal）
- 已安装依赖（requirements.txt）
- 已下载模型到本地缓存（all-mpnet-base-v2, bge-reranker-base）
- 数据已建库（data/research.db + data/chroma/）

### 10.2 启动命令
```bash
# 1. 进入项目目录
cd ~/sciPal

# 2. 激活虚拟环境
source venv_sciPal/bin/activate

# 3. 配置 LLM（二选一）
# 方式A：本地 Ollama
export SCIPAL_LLM_PROVIDER=ollama
export SCIPAL_LLM_MODEL=qwen2.5:14b

# 方式B：DeepSeek 云端
export SCIPAL_LLM_PROVIDER=openai
export SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
export SCIPAL_LLM_API_KEY=sk-你的Key
export SCIPAL_LLM_MODEL=deepseek-chat

# 4. 启动服务（必须加离线环境变量）
TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python api_server.py
```

### 10.3 启动后访问
- 首页（检索）：http://localhost:5000/
- AI 问答：http://localhost:5000/qa.html
- 综述生成：http://localhost:5000/review.html
- 健康检查：http://localhost:5000/api/health
- LLM 状态：http://localhost:5000/api/qa/status

### 10.4 建库流程（首次或数据更新后）
```bash
# 1. 建库（解析 PDF → 写入 SQLite）
python -m build_db.build_database

# 2. 去重
python build_db/dedup_papers.py data/research.db --apply

# 3. 构建向量索引
TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python -m build_db.build_embeddings

# 4. 构建 FTS 索引
python -m build_db.build_fts

# 5. 构建知识图谱
python -m build_db.build_paper_graph --apply

# 6. 自检
TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python3 scripts/self_check.py
```

---

## 十一、关键技术决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 解析器主方案 | Docling + GROBID 增强 | Docling 解析段落/图表/章节层级效果好；GROBID 元数据/参考文献更准 |
| 向量库 | Chroma | 轻量、本地、Python 友好，101 篇论文完全够用 |
| embedding 模型 | all-mpnet-base-v2 | 英文文献上效果好，模型小（0.4GB），加载快 |
| rerank 模型 | BAAI/bge-reranker-base | Cross-Encoder 重排序效果好，中英文都支持 |
| LLM 客户端 | 统一 LLMClient（OpenAI 兼容） | 一套代码支持本地 Ollama + DeepSeek + OpenAI + 任何兼容服务 |
| 问答语言 | 英文优先 | 文献是英文的，英文回答更准确、更学术 |
| PDF 渲染 | 浏览器原生 iframe | 替代 PDF.js，渲染清晰（矢量），无需维护前端 PDF 库 |
| 前端框架 | 原生 HTML + Vanilla JS | 轻量、无构建步骤、当前需求够用 |
| 后端框架 | Flask | 轻量、Python 生态好、单线程运行避免 PyTorch 死锁 |
| 数据库 | SQLite | 轻量、本地、单文件、101 篇论文完全够用 |
| 检索融合 | RRF（Reciprocal Rank Fusion） | 简单有效，不需要调权重（V25.19 后加了动态权重） |
| 多样性去重 | MMR（Maximal Marginal Relevance） | 经典算法，平衡相关性与多样性 |

---

## 十二、废弃代码清理建议（待执行）

以下模块/文件可能已不再使用，建议在确认后清理：

### 高置信度可清理
- `services/l3/`（空目录）
- `services/user/`（空目录）
- `frontend/vendor/pdf.min.js` + `pdf.worker.min.js`（V25.14 后不再使用）
- `frontend/src/pdf_annotator.js`（V25.14 后标注功能移除）

### 需确认后清理
- `services/ai/`（旧版 AI 服务，确认是否被 review/qa 完全替代）
- `services/query/search_service.py`（旧版检索服务，确认是否被 search/ 替代）
- `routes/`（旧版蓝图，确认是否在 api_server.py 中注册）
- `app.py`（**已删除**，2026-10-24 移除；主入口统一为 `api_server.py`）
- `services/pdf/annotator.py`（标注后端，前端已移除，确认是否需要保留）
- `AI_API_KEY`/`AI_MODEL`/`AI_BASE_URL` 旧版环境变量（确认是否还在使用）

### 清理前必须做
1. 全局搜索引用，确认没有其他模块依赖
2. 运行自检脚本，确认清理后所有检查通过
3. 备份原文件，确认无误后再删除

---

## 十三、版本迭代规则

1. **版本号规则**：大版本号 V10 固定，后续小版本递增（V10.1, V10.2, ...）
   - 实际执行中：V25.x 是检索/综述阶段，V26.x 是问答阶段，V27.x 将是图谱可视化
2. **每次修改必须**：
   - 递增版本号（VERSION 文件）
   - 更新 WORKLOG.md（记录变更内容、原因、验证方式）
   - 更新本文档（ARCHITECTURE.md，如果架构有变化）
   - 更新自检脚本（self_check.py，新增检查项）
   - 运行自检，确认所有检查通过
3. **Bug 修复**：小版本 +1（如 V26.1 → V26.2）
4. **新功能**：小版本 +1（如 V26.0 → V26.1），大功能可考虑大版本 +1
5. **破坏性变更**：大版本 +1，并在 WORKLOG 中明确说明迁移方法

---

**文档结束。如有遗漏或错误，请及时更新此文档。**

---

## 十四、历史迁移经验（2026-11）

早期 WorkBuddy / CodeBuddy 交接文档已移入
[`archive_legacy/`](docs/archive_legacy/README.md)，不再作为配置依据。

保留下来、仍然有效的科研与工程要求：

1. **可溯源**：paper → section → paragraph → sentence 必须可回查；
   PDF 保留 page/bbox，XML 保留 XPath/source_path。
2. **证据优先**：claim 必须绑定 quote/evidence，没有证据不写断言。
3. **源特征不强行归一化**：XML 与 PDF 各自保留结构；没有坐标就标
   `coordinate_source=unavailable`，不伪造。
4. **本地优先与可审计**：支持离线/本地模型；关键裁决写事件表，不覆盖历史。
5. **多用户隔离**：users / workspaces / memberships，按 workspace 隔离数据。

工程教训：

```text
两个写者同时改同一工作树 → 冲突；保持一个活动写者、一个 PR 一个主题。
PyTorch + Flask 多线程 → 可能死锁；重排放到独立 worker/服务。
旧 V33.13 SQLite/Windows 安装文档 → 已过时，归档，不复制其路径和配置。
```

