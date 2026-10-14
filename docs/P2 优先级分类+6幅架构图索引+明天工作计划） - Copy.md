# Sci-Pal 系统优化工作备忘录

> **创建时间：** 2026-10-04
> **当前版本：** V33.3（混合检索系统 P0+P1+P2 已完成）
> **文档目的：** 记录系统所有待优化项，按优先级分类，配合 6 幅架构图使用
> **核心原则：** 检索层不改，只改数据层；只更新向量库，主程序搜索逻辑一行都不用改

---

## 📊 系统现状总览

### 三层链路实现状态

| 链路 | 模块数 | 已实现 | 部分实现 | 待实现 | 完成度 |
|------|--------|--------|----------|--------|--------|
| 🦴 核心链路 | 7 | 5 | 2 | 0 | 85% |
| 🔧 支撑链路 | 5 | 1 | 2 | 2 | 40% |
| 🎨 体验链路 | 4 | 3 | 0 | 1 | 75% |
| **合计** | **16** | **9** | **4** | **3** | **72%** |

### 核心结论

- **总架构没问题，骨架是对的**
- **核心链路**决定能不能叫科研级（已基本完成）
- **支撑链路**决定能不能长期科研级（缺可观测性和反馈闭环）
- **体验链路**决定用户爱不爱用（可后置）

---

## 🎯 P0 优先级（必须先做，影响核心可信度）

### P0-1：EvidenceCard 去重与置信度

**问题：**
- 同一篇论文的不同段落、不同论文的相似结论，可能生成重复证据
- 导致生成时引用冗余，低质量证据污染生成

**优化内容：**
1. **唯一标识：** EvidenceCard 增加 `source_paper_id` + `section` + `span` 唯一标识
2. **语义去重：** embedding 相似度 > 0.9 的 EvidenceCard 合并，保留更权威来源
3. **置信度字段：** 增加 `confidence` 字段，综合计算：
   - 来源类型（全文/摘要）权重
   - 匹配方式（向量/BM25/实体）权重
   - 重排分数（bge-reranker 输出）
4. **生成时按置信度排序：** 低置信度证据明确标注，高置信度优先引用

**涉及文件：**
- `services/review/models.py`（EvidenceCard 数据模型增强）
- `services/review/evidence_extractor.py`（去重逻辑）
- `services/review/review_generator.py`（生成时按置信度排序）

**当前状态：** ⚠️ 待实现

---

### P0-2：证据不足时的 fallback 机制

**问题：**
- 某个章节检索不到证据时，系统要么硬编（生成无关内容），要么卡死
- 目前流程里没有明确的 fallback

**优化内容：**
1. **证据充足性检查：** 每个章节生成前，检查 `assigned_evidence_ids` 数量与多样性
2. **不足时触发二次检索：** 自动用 `章节标题 + 关键词` 作为 query 补充检索
3. **降级策略：** 二次检索仍不足时，降级为"综述性描述 + 明确标注无直接证据"，不硬编
4. **用户提示：** 前端提示用户"该章节证据不足，是否需要手动补充文献？"

**涉及文件：**
- `services/review/review_generator.py`（evidence_sufficiency_check + fallback）
- `frontend/src/outline_editor.js`（前端提示）
- `frontend/review.html`（UI 展示）

**当前状态：** ⚠️ 待实现

---

## 🎯 P1 优先级（重要，影响长期可维护性）

### P1-1：检索可观测性面板

**问题：**
- 检索链路很长（query扩展→NER→混合搜索→rerank→MMR→上下文扩展→图谱扩展）
- 每一环都可能成为瓶颈或误差源，没有可观测性，调参全靠猜

**优化内容：**
1. **记录每次检索的完整链路：**
   - 原始 query
   - 扩展词（query_expander 输出）
   - NER 提取的实体（scispacy 输出）
   - 各路召回结果（向量 top-k / BM25 top-k / 实体匹配 hits）
   - RRF 融合后的排名
   - rerank 前后排名变化
   - MMR 去重后的最终结果
   - 最终被引用的证据来源统计
2. **可观测性 API：** 新增 `/api/debug/retrieval/{task_id}` 接口，返回某次检索的完整链路数据
3. **前端调试面板：** 综述生成页增加"检索调试"面板，可视化展示每路召回的命中率、重排前后排名变化
4. **调参辅助：** 标记"召回不到"还是"重排排错"，方便定位问题

**涉及文件：**
- 新建 `services/search/retrieval_observability.py`（可观测性核心）
- `services/search/unified_retriever.py`（埋点记录）
- `services/search/hybrid_search.py`（埋点记录）
- `services/search/reranker.py`（埋点记录）
- `api_server.py`（新增调试 API）
- `frontend/review.html`（调试面板 UI）

**当前状态：** ⚠️ 待实现

---

### P1-2：句子关系判定（增量更新核心）

**问题：**
- 新论文进来后，不知道新句子和旧句子是什么关系
- 是重复、补充、支持、反驳，还是更新？没有判定机制

**优化内容：**
1. **5 种关系类型判定：**

| 关系 | 判定方式 | 处理动作 |
|------|----------|----------|
| 🔴 重复 | embedding 相似度 > 0.95，结论一致 | 合并，保留更权威来源 |
| 🟡 补充 | 相似度 0.8~0.95，不同角度 | 挂到同一 EvidenceCard |
| 🟢 支持 | 结论一致 + 独立来源 | 增加证据强度 |
| 🩷 反驳 | 结论相反（LLM判断） | 标记冲突，触发复核 |
| 🔵 更新 | 新结论取代旧结论 | 旧句子标记 deprecated |

2. **规则兜底（快速判定）：** 相似度 > 0.95 直接判重复；同 paper_id 不判关系
3. **LLM 深度判定（0.8~0.95 区间）：** 用 Ollama Qwen2.5 判断关系类型 + 置信度 + 理由
4. **置信度计算：** confidence = 0.5×相似度 + 0.3×LLM置信度 + 0.2×来源权威度
5. **批量处理：** 所有 candidate_pairs 批量送 LLM，减少调用次数

**涉及文件：**
- 新建 `services/search/sentence_relation_classifier.py`（关系判定核心）
- `services/search/unified_retriever.py`（近邻检索复用）
- `services/review/llm_client.py`（LLM 调用）

**当前状态：** ⚠️ 待实现（增量更新的核心难点）

---

### P1-3：EvidenceCard 增量维护

**问题：**
- 新论文进来后，EvidenceCard 怎么增量更新？
- 是 append 到已有卡片，还是 create 新卡片，还是 flag 冲突？

**优化内容：**
1. **5 种增量操作：**
   - **append（补充/支持）：** 新句子追加到已有 EvidenceCard 的 supporting_sentences
   - **create（新主题）：** 相似度 < 0.8 或新发现，创建新 EvidenceCard
   - **flag（反驳/冲突）：** 标记 conflict_flag，记录冲突句子ID
   - **deprecated（更新/取代）：** 旧 EvidenceCard 标记 superseded，记录 superseded_by
   - **merge（重复）：** 不创建新卡片，新句子标记 duplicate_of
2. **EvidenceCard 字段增强：** 增加 version、source_paper_ids[]、support_count、conflict_flags[]、deprecated_status、superseded_by、last_updated
3. **增量管理器：** 统一管理 EvidenceCard 的增删改，保证一致性

**涉及文件：**
- 新建 `services/review/evidence_card_incremental_manager.py`（增量管理核心）
- `services/review/models.py`（EvidenceCard 字段增强）

**当前状态：** ⚠️ 待实现

---

## 🎯 P2 优先级（重要但不紧急，可后续做）

### P2-1：用户反馈闭环

**问题：**
- 目前流程是单向的：检索→生成→评审→输出
- 用户对生成结果的修改、对引用错误的纠正，没有回流到系统

**优化内容：**
1. **user_feedback 表：** 记录用户修改（original vs edited）、修改类型（内容/引用/结构）、修改时间
2. **反馈回流：**
   - 引用错误纠正 → 用于微调 reranker 权重
   - 内容修改 → 用于优化 prompt 和评分标准
   - 高频修改的章节 → 标记为"生成质量差"，重点优化
3. **主动学习：** 积累足够反馈后，可做 DPO/RLHF 微调生成模型
4. **反馈统计面板：** 展示用户修改统计、高频问题、生成质量趋势

**涉及文件：**
- 新建 `services/feedback/user_feedback.py`（反馈管理）
- 数据库新增 `user_feedback` 表
- `frontend/review.html`（修改时自动记录反馈）

**当前状态：** ⚠️ 待实现

---

### P2-2：版本管理与增量同步

**问题：**
- 数据源层有 download_* 脚本，但没有增量更新策略
- PubMed/arXiv 每天都有新论文，每次全量重建向量库成本很高

**优化内容：**
1. **last_sync 时间戳：** 每个数据源记录 last_sync，只拉取增量（上次同步之后的新论文）
2. **版本管理：** 每个论文记录 version，更新时版本号递增，旧版本标记 superseded
3. **向量库 upsert：** ChromaDB 支持按 ID upsert，不需要全量重建
4. **增量同步任务：** 支持定时任务（每天/每周自动同步新论文）
5. **同步日志：** 记录每次同步的新增/更新/失败数量，可追溯

**涉及文件：**
- 新建 `services/data/incremental_sync.py`（增量同步核心）
- `download_pubmed_abstracts.py`（增加 last_sync 支持）
- `download_pmc_xml.py`（增加 last_sync 支持）
- `build_paragraph_vector_index.py`（增加 upsert 模式）

**当前状态：** ⚠️ 待实现（断点续传已有，last_sync 待补充）

---

### P2-3：影响范围评估 + 局部重算

**问题：**
- 新证据进来后，可能只影响某些章节，但目前是全局重跑
- 性能浪费，增量更新体验差

**优化内容：**
1. **受影响章节识别：** 根据 EvidenceCard 挂载的章节，找出 assigned_evidence_ids 发生变化的章节
2. **传播影响：** 相邻章节的上下文（渐进式上下文注入）可能受影响，标记为"可能受影响"
3. **局部重算：** 只重新生成受影响章节，未受影响章节直接复用上次结果
4. **引用编号更新：** 局部重算后更新全文引用编号，保证对应
5. **变更日志：** 记录本次增量更新影响了哪些章节、新增了哪些证据，生成"更新摘要"

**涉及文件：**
- `services/review/review_generator.py`（局部重算逻辑）
- 新建 `services/review/impact_analyzer.py`（影响范围评估）

**当前状态：** ⚠️ 待实现（性能优化关键）

---

### P2-4：错误处理与重试（全面补充）

**问题：**
- 在线搜索已有 3 次重试，下载已有失败重试
- 但其他模块（LLM 调用、解析器、数据库操作）缺少统一的错误处理

**优化内容：**
1. **统一重试装饰器：** @retry(max_retries=3, backoff=2) 装饰器，支持指数退避
2. **LLM 调用重试：** Ollama 调用失败时自动重试，超时降级到更小模型
3. **解析器 fallback：** Docling 失败时自动 fallback 到 MinerU，再失败 fallback 到 pdfplumber
4. **死信队列：** 多次失败的任务进入 dead_letter_queue，不阻塞主流程，可人工处理
5. **错误统计：** 记录各模块的错误率、失败原因，方便定位稳定性问题

**涉及文件：**
- 新建 `utils/retry.py`（统一重试装饰器）
- 新建 `utils/dead_letter_queue.py`（死信队列）
- `services/review/llm_client.py`（LLM 重试+降级）
- `build_db/parsers/parser_orchestrator.py`（解析器 fallback 链）

**当前状态：** 🔶 部分实现（在线搜索/下载已有，其他待补充）

---

### P2-5：结构化日志与监控

**问题：**
- 目前只有 print 日志，缺少结构化日志和监控
- 出问题时难以定位是哪个模块、哪个环节失败

**优化内容：**
1. **结构化日志：** 用 Python logging 模块，JSON 格式输出，包含时间、模块、级别、消息、上下文
2. **日志分级：** DEBUG / INFO / WARNING / ERROR / CRITICAL，可配置级别
3. **耗时统计：** 每个模块的输入输出、耗时、成功率自动记录
4. **监控面板：** 前端增加"系统监控"面板，展示各模块的 QPS、耗时、错误率、当前任务数
5. **告警：** 错误率超过阈值时自动告警（前端提示/日志标记）

**涉及文件：**
- 新建 `utils/structured_logger.py`（结构化日志）
- 新建 `utils/monitor.py`（监控统计）
- `api_server.py`（请求耗时中间件）
- `frontend/admin.html`（监控面板，新建）

**当前状态：** 🔶 部分实现（print 日志已有，结构化待实现）

---

### P2-6：导出与分享功能

**问题：**
- 生成的综述目前只能在前端查看，缺少导出功能
- 用户需要导出为 Markdown / PDF / 统计报告

**优化内容：**
1. **Markdown 导出：** 综述内容导出为标准 Markdown，保留引用标记和章节结构
2. **PDF 导出：** 用 weasyprint 或 wkhtmltopdf 将综述渲染为 PDF，支持自定义模板
3. **统计报告导出：** 生成综述的统计报告（引用论文数、章节分布、证据来源分布、置信度统计）
4. **分享链接：** 生成只读分享链接，可设置有效期和密码
5. **BibTeX 导出：** 参考文献导出为 BibTeX 格式，方便导入 Zotero/EndNote

**涉及文件：**
- 新建 `services/export/exporter.py`（导出核心）
- 新建 `services/export/markdown_exporter.py`
- 新建 `services/export/pdf_exporter.py`
- 新建 `services/export/bibtex_exporter.py`
- `frontend/review.html`（导出按钮 UI）

**当前状态：** ⚠️ 待实现

---

## 📋 已完成的优化（V31 ~ V33 回顾）

### V31.x 系列 — 综述生成核心修复
- ✅ V31.82：综述生成跳过关系抽取和冲突检测（这些是问答功能用的）
- ✅ V31.83-V31.86：方案A — search_and_assign_papers 按大纲搜索并分配论文，从段落构造证据卡片直接分配到章节
- ✅ EvidenceCard pydantic 验证错误修复
- ✅ 生成内容跟章节标题不相关的问题修复（按章节主题检索而非综述主题）

### V32.x 系列 — 大纲模板化+代码优化+数据扩充
- ✅ V32.1：去掉"自动生成大纲"按钮，用预设模板替代（系统综述型/叙事型/方法学型）
- ✅ V32.3：修复 handleTemplateSelect 不是 async 但用了 await 的语法错误
- ✅ V32.4：自动从综述主题提取核心关键词注入每章搜索词（修复 Chapter 5 内容跟 STAT1 不相关）
- ✅ V32.5：代码优化三大升级 — 分章节生成+渐进式上下文注入、章节类型感知、证据-声明矩阵、迭代精炼+5维评分标准引导
- ✅ V32.6-V32.8：数据扩充工具集 — download_openalex.py、build_abstracts_db.py 的 embedding 模型改成 bge-base-en-v1.5
- ✅ V32.9：PMC 全文下载增强 — 下载后检查 XML 是否有 `<body>` 标签，没有的自动删除（过滤只有摘要的文章）；新增 batch_download_pmc.py

### V33.x 系列 — 混合检索系统
- ✅ V33.0：Windows 控制台编码问题修复 — 强制 utf-8 + subprocess 设置 PYTHONIOENCODING
- ✅ V33.1（P0）：online_search.py（NCBI E-utilities 封装）、hybrid_retriever.py（并行搜索本地+在线，三级去重）
- ✅ V33.2（P1）：online_downloader.py（异步下载器，三阶段流水线）、前端搜索页改造（在线搜索开关、在线文献勾选下载、下载进度条）
- ✅ V33.3（P2）：5项优化 — Toast 通知、下载历史记录、下载失败重试、批量队列管理、配置面板

---

## 🗺️ 架构图索引（6 幅）

| 编号 | 图名 | 视角 | 重点 | 文件 |
|------|------|------|------|------|
| 图1 | 核心数据流图（简略版） | 横向：数据流动 | 每个 py 文件干什么 | `sci-pal-dataflow-v2.html` |
| 图2 | 完整系统架构图（7层） | 纵向：系统分层 | 每层用了什么技术/算法/方法 | `sci-pal-architecture-v2.html` |
| 图3 | PDF 解析器专项图 | 深度：PDF 解析子系统 | 6 大解析引擎的技术细节/算法/配置 | `sci-pal-pdf-parsers-architecture.html` |
| 图4 | 超完整数据流图 | 横向+深度：全流程 | 从 PDF 解析 6 大引擎到前端，全部细节 | `sci-pal-full-dataflow-with-parsers.html` |
| 图5 | 三层链路架构图 ⭐ | 核心/支撑/体验 | 含每个模块实现状态，优先级建议 | `sci-pal-three-layer-architecture.html` |
| 图6 | 增量更新层详细子图 ⭐ | 增量更新 8 步流程 | 5 种关系判定，4 大设计原则 | `sci-pal-incremental-update-subgraph.html` |

**使用建议：**
- 平时主力看**图4（超完整数据流图）**，一图从 PDF 解析到前端
- 想深入理解 PDF 解析看**图3（专项图）**
- 想了解系统分层看**图2（架构图）**
- 规划优化优先级看**图5（三层链路图）**
- 实现增量更新看**图6（增量更新子图）**

---

## 📝 明天的工作计划建议

### 第一天：P0 优先级（2 项）
1. **P0-1：EvidenceCard 去重与置信度**
   - 修改 models.py 增加字段
   - 修改 evidence_extractor.py 增加去重逻辑
   - 修改 review_generator.py 生成时按置信度排序
2. **P0-2：证据不足 fallback 机制**
   - 在 review_generator.py 增加 evidence_sufficiency_check
   - 不足时触发二次检索
   - 降级为"综述性描述 + 明确标注"

### 第二天：P1 优先级（3 项，可分 2-3 天）
1. **P1-1：检索可观测性**（新建模块，工作量较大）
2. **P1-2：句子关系判定**（增量更新核心，需要 LLM 调用）
3. **P1-3：EvidenceCard 增量维护**（依赖 P1-2 的关系判定结果）

### 第三天及以后：P2 优先级（6 项，按需做）
- P2-1：用户反馈闭环
- P2-2：版本管理与增量同步
- P2-3：影响范围评估+局部重算
- P2-4：错误处理与重试（全面补充）
- P2-5：结构化日志与监控
- P2-6：导出与分享功能

---

## 🔑 核心原则备忘（反复强调）

1. **检索层不改，只改数据层** — 只更新向量库，主程序搜索逻辑一行都不用改
2. **SQLite 管内部关系，向量库管语义检索** — 两者靠文章 ID 挂钩
3. **综述生成不需要关系抽取和冲突检测** — 那些是问答/分析功能用的（V31.82 已完全跳过）
4. **新工作流：选模板→编辑关键词→按大纲搜索并分配→生成综述** — 去掉了"自动生成大纲"
5. **已保存的 7 章节大纲不能删** — 必须在下拉菜单的"已保存大纲"分组里显示
6. **不用多智能体架构** — 有精确数据库不需要，采用其他 5 条优点（大纲先行、大纲引导检索、分章节生成+渐进式上下文、迭代精炼+评分、证据-声明矩阵）
7. **PMC 全文下载要过滤掉只有摘要的文章** — 检查 XML 是否有 `<body>` 标签
8. **增量更新的本质不是"加新论文"，而是"让新句子和旧句子建立关系，并更新 EvidenceCard"**
9. **增量更新 4 大原则：** 不重建只追加+标记、关系判定用 LLM+规则、EvidenceCard 是增量单位、增量要有影响范围评估
10. **版本号规则：** 大版本 V10，后续小版本按序列递增（如 V10.1、V10.2）— 实际项目用 V25.x/V31.x/V32.x/V33.x 系列

---

## 📌 备注

- 本文档配合 6 幅架构图使用，图里有更直观的可视化展示
- 每次修改后，同步更新说明手册、测试工作流脚本和自检脚本（用户偏好）
- 完成"词源智能 RAG 项目"后，继续开发"PDF 端口设计"方案，用于处理 Cell、Nature、Science 等期刊的论文数据（用户偏好）
- 有问题随时对照架构图和本文档，先定位是哪个链路、哪个模块的问题

---

**文档结束。先休息，明天再战！💪**
