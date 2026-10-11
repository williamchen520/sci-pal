# Sci-Pal 工作日志

## 📅 2026-10-04

### ⚠️⚠️⚠️ 核心原则（反复强调！）⚠️⚠️⚠️

**只更新向量库，主程序搜索逻辑一行都不用改！**

---

#### 为什么？

1. **主程序搜索时，是去向量库里查，不是去 SQLite 里查！**
2. **向量库是主程序的数据源！**
3. **数据源里多了数据，主程序自然就能搜到！**

---

#### 正确的架构：

- **SQLite**：管内部关系（段落结构、图表、表格、引用、主题分类）
- **向量库（ChromaDB）**：管语义检索（哪段文字跟查询最像）
- **两者通过文章 ID 关联**
- **主程序只跟向量库交互，不直接跟 SQLite 交互**

---

#### 新增数据的正确流程：

1. 把新数据存到 SQLite（管内部关系）
2. 用跟老库一样的 Embedding 模型算向量
3. 批量插进主程序的向量库（ChromaDB）
4. 把元数据（标题、作者、ID、paper_id）一起写进向量的 metadata
5. **完成！主程序一行都不用改！**

---

#### 关键点：

1. **Embedding 模型必须一致**：新数据用的向量模型，必须跟老库一模一样（bge-base-en-v1.5）
2. **文章 ID 对得上**：向量库 metadata 里存的 paper_id，要能对应回 SQLite 里的记录
3. **主程序搜索逻辑不用改**：只要向量库更新了，检索接口自然能搜到新文章

---

### ❌ 我们之前走歪的方案（统一检索）

- 建联合索引（unified.db）
- 写新的检索层（unified_search.py）
- 写新的混合检索（hybrid_search_v2.py）
- 把新检索层接入主程序（改 api_server.py + review_generator.py）
- 然后遇到各种 bug（FTS5 查询错误、EvidenceCard 验证错误、接口不兼容...）
- **把简单的问题复杂化了！**

---

### ✅ 我们现在回退到正确的道路上

1. ✅ 主程序回退到旧的检索层（V31.71）
2. ✅ XML 相关代码都保留（下载脚本、解析脚本、建库脚本）
3. 🚀 只需要写一个脚本，把 xml.db 的向量批量插进向量库
4. ✅ 主程序的搜索逻辑一行都不用改！

---

### 📊 时间线回顾

| 阶段 | 版本 | 状态 | 内容 |
|------|------|------|------|
| 旧系统（可以用） | V31.29 之前 | ✅ 正常 | 解耦工作（按章节生成、校验解耦、并行校验、双模型） |
| 旧系统增强 | V31.30~V31.32 | ✅ 正常 | 句子级切分和关联关系 |
| XML 数据库开始 | V31.33~V31.59 | 📦 新增（没接入主程序） | 下载 XML、解析 XML、建 xml.db、建联合索引、写新检索层 |
| 接入主程序（出问题） | V31.60~V31.70 | ❌ 出问题 | 把新检索层接入 api_server.py，遇到各种 bug |
| 回退检索层 | V31.71 | ✅ 恢复正常 | 回退到旧的检索层，主程序恢复正常 |

---

### 🎯 后续计划

1. 测试主程序是不是恢复正常
2. 写脚本把 xml.db 的向量批量插进向量库（data/chroma/）
3. 测试主程序能不能检索到 XML 数据库的内容
4. 完成！

---

## ⚠️⚠️⚠️ 再次强调！⚠️⚠️⚠️

**只更新向量库，主程序搜索逻辑一行都不用改！**

**SQLite 管内部关系，向量库管语义检索，两者靠文章 ID 挂钩！**

**不要走统一检索的歪路！不要写新的检索层！不要改主程序的搜索逻辑！**

---

## 📅 2026-10-09

### 🚀 V33.4: P0 优先级优化完成

根据架构评审后的优化备忘录，完成 P0 优先级的两项核心优化：

---

#### ✅ P0-1: EvidenceCard 去重与置信度

**问题**：
- 同一篇论文的不同段落、不同论文的相似结论，可能生成重复证据
- 证据卡片没有来源类型、匹配方式、重排分数等元数据
- 生成时无法按证据质量排序，低质量证据可能污染生成

**修改文件**：
1. `services/review/models.py`
   - EvidenceCard 增加 5 个新字段：
     - `source_type`: 来源类型（full_text / abstract）
     - `match_method`: 匹配方式（vector / bm25 / entity / hybrid）
     - `rerank_score`: 重排分数（0-1，bge-reranker-base 输出）
     - `dedupe_key`: 去重 key（paper_id + para_id 的哈希）
     - `retrieval_rank`: 检索排名（在召回结果中的位置）
   - 新增 `compute_quality_score()` 方法：
     - 综合质量分 = 0.4×来源类型权重 + 0.3×匹配方式权重 + 0.3×重排分数
     - 来源类型权重：full_text=1.0, abstract=0.6
     - 匹配方式权重：hybrid=1.0, vector=0.8, bm25=0.7, entity=0.6

2. `services/review/evidence_extractor.py`
   - `extract_from_paragraphs()` 增加精确去重：
     - 基于 paper_id + para_id 去重，避免同一段落重复生成证据
     - 去重时打印跳过数量，方便调试
   - 从段落元数据中提取来源/匹配信息（如果检索层传入了的话）
   - 抽取完成后按综合质量分降序排列（高质量证据优先）

---

#### ✅ P0-2: 证据不足时的 fallback 机制

**问题**：
- 之前某个章节检索不到证据时，直接跳过该章节，导致综述缺章
- 用户不知道为什么章节缺失，也没有提示需要补充文献
- 证据不足时没有降级方案，系统要么硬编，要么卡死

**修改文件**：
1. `services/review/review_generator.py`
   - `_write_draft()` 增加证据不足检测：
     - 每章最少证据数阈值：2 条（可配置）
     - 证据不足时不再跳过，而是触发 fallback
     - 记录证据不足的章节列表，用于最终警告
   - 新增 `_generate_fallback_section()` 方法：
     - 基于章节标题和描述生成综述性概述
     - 明确标注"本章直接证据有限"，避免幻觉
     - 不做具体实验数据引用（因为没有证据）
     - 引导读者参考其他章节或进一步查阅文献
     - 支持英文/中文双语 prompt
     - LLM 调用失败时的最终降级：返回简单提示文本
   - 新增 `get_insufficient_evidence_sections()` 公开方法：
     - 获取最后一次生成中证据不足的章节列表
     - 供前端和 API 层调用，展示警告信息
   - fallback 章节的句子标记为 UNVERIFIED 状态，备注"证据不足 fallback 章节"

---

#### 📊 优化效果

| 优化项 | 之前 | 之后 |
|--------|------|------|
| 重复证据 | 可能重复，引用冗余 | 精确去重，基于 paper_id+para_id |
| 证据质量 | 无区分，随机排序 | 综合质量分，按质量排序 |
| 证据不足 | 直接跳过，章节缺失 | fallback 生成综述性概述 + 警告 |
| 用户感知 | 不知道为什么缺章 | 明确提示哪些章节证据不足 |
| 幻觉风险 | 可能硬编内容 | 明确标注"直接证据有限" |

---

#### 🎯 后续计划（P1/P2）

**P1 优先级**：
1. 检索可观测性面板——记录每次检索的 query/扩展词/各路召回/重排分数/最终入选证据
2. 句子关系判定——5种关系（重复/补充/支持/反驳/更新），规则兜底+LLM深度判定
3. EvidenceCard 增量维护——append/create/flag冲突/deprecated/merge

**P2 优先级**：
1. 用户反馈闭环——记录用户修改，用于微调 reranker/prompt
2. 版本管理与增量同步——last_sync 时间戳，向量库 upsert
3. 影响范围评估+局部重算——只重算受影响章节
4. 错误处理与重试——统一重试装饰器，LLM调用重试+降级
5. 结构化日志与监控——JSON格式结构化日志
6. 导出与分享功能——Markdown/PDF/统计报告/BibTeX导出

---

#### ⚠️ 核心原则（继续保持）

1. **检索层不改，只改数据层**——只更新向量库，主程序搜索逻辑一行都不用改
2. **综述生成不需要关系抽取和冲突检测**——这些是问答/分析功能用的
3. **证据锚定生成**——任何结论，没有 EvidenceCard 就禁止写入综述正文
4. **证据不足时降级，不硬编**——明确标注"直接证据有限"，避免幻觉

---

## 📅 2026-10-10

### 🚀 V33.5: P1 优先级优化完成

在 P0（EvidenceCard 去重与置信度、证据不足 fallback）的基础上，完成 P1 三项核心优化，全部通过功能测试。

---

#### ✅ P1-1: 检索可观测性模块（retrieval_observability.py）

**新建文件**：`services/search/retrieval_observability.py`

**问题**：
- 检索链路很长（query扩展 → 实体提取 → 向量召回 → BM25召回 → 实体匹配 → 图谱遍历 → 重排 → MMR多样性），每一环都可能成为瓶颈或误差源
- 没有可观测性，调召回、调重排、调 prompt 全靠猜
- 无法定位是"召回不到"还是"重排排错"

**核心功能**：
1. **完整记录每次检索**：
   - 基本信息：record_id, task_id, review_id, timestamp
   - 查询信息：original_query, expanded_queries, key_entities, entity_hits
   - 召回信息：各路召回结果（vector/bm25/entity/graph/abstract），包含数量、Top10 ID、平均分、最高分
   - 重排信息：rerank_model, 输入/输出数量, 每个 para_id 的分数, Top10 分数
   - MMR 多样性：输入/输出数量, lambda 参数
   - 最终结果：段落数, 证据数, 论文ID列表, 证据ID列表
   - 耗时：各阶段耗时（毫秒），总耗时
2. **查询接口**：
   - `get_record(record_id)`：按 ID 查询单条记录
   - `get_by_task_id(task_id)`：按任务 ID 查询所有相关记录
   - `get_by_review_id(review_id)`：按综述 ID 查询所有相关记录
   - `list_recent(n)`：列出最近的 N 条记录
3. **统计分析**：
   - `get_stats(last_n)`：平均召回数、平均重排输入/输出、平均最终证据数、各路召回贡献占比、平均耗时、异常统计
4. **深度分析**：
   - `analyze_retrieval(record_id)`：自动诊断检索问题，返回 status（good/warning/critical）、问题列表、改进建议
   - 检查项：召回是否充足、各路召回是否均衡、重排是否正常、最终结果是否为空、耗时是否过长、摘要库搜索是否出错
5. **持久化存储**：
   - JSON 文件存储，每条记录一个文件
   - 索引文件快速查询
   - 最多保留 1000 条记录（可配置）
   - 线程安全，支持并发访问

**测试结果**：
- ✅ 记录创建、查询、统计、深度分析全部通过
- ✅ 各路召回贡献占比计算正确（vector 62.5%, bm25 37.5%）

---

#### ✅ P1-2: 句子关系判定器（sentence_relation_classifier.py）

**新建文件**：`services/search/sentence_relation_classifier.py`

**问题**：
- 新论文进来后，不知道新句子和旧句子是什么关系
- 是重复、补充、支持、反驳还是更新？
- 纯向量相似度不够，需要 LLM 判断语义关系

**5种关系类型**：
| 关系 | 英文 | 判定规则 | 颜色 |
|------|------|----------|------|
| 重复 | duplicate | 相似度 > 0.95，内容几乎完全相同 | 灰色 |
| 补充 | supplement | 相似度 0.8-0.95 + 不同角度/侧重点 | 蓝色 |
| 支持 | support | 相似结论 + 独立来源（不同论文） | 绿色 |
| 反驳 | contradict | 结论相反/矛盾（检测矛盾关键词对） | 红色 |
| 更新 | update | 新结论取代旧结论（时间更新 + 方法改进关键词） | 黄色 |

**核心功能**：
1. **规则兜底判定**（开销低，先执行）：
   - 语义相似度计算（支持传入 embedding 函数，默认用词重叠度 Jaccard）
   - 重复判定：相似度 > 0.95
   - 不相关判定：相似度 < 0.30
   - 矛盾关键词检测：24对矛盾关键词（increase/decrease, promote/inhibit, activate/suppress 等）
   - 支持/补充判定：相似度 0.8-0.95 + 是否来自不同论文
   - 更新关系检测：方法改进关键词 + 时间更新
2. **LLM 深度判定**（可选，仅对相似度 >= 0.6 的句子调用）：
   - 详细的 system prompt，定义6种关系类型
   - 结构化 JSON 输出（relation, confidence, reason, key_similarities, key_differences）
   - 融合规则和 LLM 结果（LLM 置信度高时用 LLM，否则用规则）
3. **批量判定**：
   - `classify_batch(pairs)`：批量判定多对句子
   - `find_relations_for_new_sentence()`：为新句子查找与已有句子的关系（Top-K）
4. **可配置**：
   - 相似度阈值全部可配置
   - 是否启用 LLM 可配置
   - LLM 调用阈值可配置（避免对不相关句子浪费 LLM 调用）

**测试结果**：
- ✅ 反驳关系检测正确（increase/decrease 矛盾关键词对）
- ✅ 更新关系检测正确（improved/outperforms + 时间更新）
- ✅ 不相关判定正确
- ✅ 关系类型中文标签正确

---

#### ✅ P1-3: EvidenceCard 增量维护管理器（evidence_card_incremental_manager.py）

**新建文件**：`services/review/evidence_card_incremental_manager.py`

**问题**：
- 新论文进来后，EvidenceCard 怎么增量维护？
- 是创建新卡片、追加到已有卡片、合并相似卡片，还是标记旧卡片失效？
- 怎么追踪版本历史？怎么评估影响范围？

**5大核心操作**：
| 操作 | 说明 |
|------|------|
| create | 创建新的 EvidenceCard |
| append | 把新证据追加到已有卡片（同一主题的补充证据） |
| merge | 合并多个相似的证据卡片（3种策略：拼接/保留最长/保留最高质量） |
| deprecate | 标记卡片为已失效（被新证据取代，保留历史不删除） |
| flag_conflict | 标记两个卡片之间存在冲突（3种类型：contradiction/inconsistency/outdated） |

**卡片状态机**：
- ACTIVE（活跃）→ 正常使用
- DEPRECATED（已失效）→ 被新证据取代，replaced_by 指向新卡片
- CONFLICT（存在冲突）→ 需要人工/LLM 复核
- MERGED（已合并）→ 已合并到其他卡片
- DRAFT（草稿）→ 待确认

**核心功能**：
1. **完整版本追踪**：
   - 每个卡片维护 versions 列表，记录每次操作的版本号、时间、操作类型、操作者、原因、变更内容
2. **冲突管理**：
   - ConflictRecord 记录冲突双方、类型、描述、置信度、解决状态、解决方案
   - 支持标记冲突、查询冲突（按是否解决、按章节过滤）
3. **操作日志**：
   - IncrementalOperationLog 记录每次操作：操作类型、目标卡片、相关卡片、时间、操作者、原因、详情、受影响章节
   - 支持按卡片ID、操作类型查询
4. **影响范围评估**：
   - `assess_impact(card_id)`：评估卡片变更的影响范围
   - 直接影响章节（卡片所在章节）
   - 间接受影响章节（同一论文的其他卡片所在章节）
   - 冲突影响（相关冲突记录）
   - 自动给出处理建议
5. **统计信息**：
   - `get_stats()`：总卡片数、各状态卡片数、未解决冲突数、追加证据总数、操作日志数、受影响章节数
6. **持久化存储**：
   - JSON 文件存储状态（card_index, conflicts, operation_logs, section_cards）
   - 线程安全，支持并发访问

**测试结果**：
- ✅ 创建、追加、冲突标记、失效标记、合并全部通过
- ✅ 版本追踪正确（创建1个版本，追加后2个版本）
- ✅ 状态机转换正确（active → deprecated/conflict/merged）
- ✅ 影响范围评估正确（直接影响章节 + 处理建议）
- ✅ 统计信息正确（5个卡片：1活跃 + 1失效 + 1冲突 + 2合并）

---

#### 📊 P1 优化效果总结

| 优化项 | 解决的问题 | 核心价值 |
|--------|-----------|----------|
| 检索可观测性 | 调参全靠猜，无法定位问题 | 每次检索全链路可追溯，自动诊断问题 |
| 句子关系判定 | 新句子和旧句子什么关系不知道 | 5种关系自动判定，规则兜底+LLM深度 |
| EvidenceCard增量维护 | 新论文怎么长进已有结构 | 5大操作+状态机+版本追踪+影响评估 |

---

#### 🎯 后续计划（P2，明天继续）

**P2 优先级**：
1. 用户反馈闭环——新建 user_feedback 表，记录用户修改，用于微调 reranker/prompt
2. 版本管理与增量同步——last_sync 时间戳，向量库 upsert，定时同步任务
3. 影响范围评估+局部重算——只重算受影响章节，不全局重跑
4. 错误处理与重试——统一重试装饰器，LLM调用重试+降级，解析器fallback链，死信队列
5. 结构化日志与监控——JSON格式结构化日志，监控面板
6. 导出与分享功能——Markdown/PDF/统计报告/BibTeX导出，分享链接

---

#### ⚠️ 核心原则（继续保持）

1. **检索层不改，只改数据层**——只更新向量库，主程序搜索逻辑一行都不用改
2. **综述生成不需要关系抽取和冲突检测**——这些是问答/分析功能用的
3. **证据锚定生成**——任何结论，没有 EvidenceCard 就禁止写入综述正文
4. **证据不足时降级，不硬编**——明确标注"直接证据有限"，避免幻觉
5. **不重建，只追加 + 标记**——旧数据不动，新数据挂上去，冲突用标记不用删除
6. **EvidenceCard 是增量单位**——不是论文，不是句子，而是 EvidenceCard

---

## 📅 2026-10-10

### 🚀 V33.6: P2 优先级优化完成

在 P0（EvidenceCard 去重与置信度、证据不足 fallback）和 P1（检索可观测性、句子关系判定、EvidenceCard 增量维护）的基础上，完成 P2 六项支撑链路优化，全部通过功能测试。

P2 优化聚焦于"让系统可调试、可进化、可维护"的支撑链路，不改变核心检索和生成逻辑。

---

#### ✅ P2-1: 用户反馈闭环模块（user_feedback.py）

**新建文件**：`services/review/user_feedback.py`

**问题**：
- 用户对生成结果的修改、对引用错误的纠正，没有回流到系统
- 系统永远停在初始版本，无法"越用越准"
- 无法统计哪些章节/论文最容易出问题

**核心功能**：
1. **11种反馈类型**：content_edit（内容修改）、citation_fix（引用修正）、section_add/delete/reorder（章节增删改序）、evidence_add/remove/reassign（证据调整）、rating（评分）、comment（评论）、other
2. **5级评分**：excellent(5) / good(4) / fair(3) / poor(2) / bad(1)
3. **文本差异记录**：original vs edited，diff_html，changed_chars，changed_ratio
4. **记录接口**：
   - `record_feedback()`：通用记录
   - `record_content_edit()`：记录内容修改（自动计算差异）
   - `record_citation_fix()`：记录引用修正
   - `record_rating()`：记录评分
   - `record_comment()`：记录评论
5. **查询接口**：按综述ID、章节ID、类型、未处理状态查询
6. **统计分析**：
   - `get_stats()`：总反馈数、各类型分布、平均评分、评分分布、内容修改率、引用修正数
   - `get_improvement_suggestions()`：基于反馈数据自动生成系统改进建议（哪些章节问题最多、哪些论文引用错误最多、平均修改率趋势）
7. **反馈处理**：标记已处理、批量标记、处理备注
8. **持久化存储**：JSON 文件，线程安全，全局单例

**已修复的 Bug**：
- **死锁问题**：`get_by_review_id()`、`get_by_section_id()`、`get_by_type()`、`get_unprocessed()` 原本在持有 `self._lock` 的情况下调用了 `get_feedback()`，而 `get_feedback()` 又尝试获取同一个锁，导致程序卡死超时。
- **修复方案**：重构为"先在锁内获取 feedback_id 列表，释放锁后再逐个调用 get_feedback()"。

**测试结果**：
- ✅ 记录评分、评论、内容修改全部通过
- ✅ 按综述/章节/类型查询正确
- ✅ 统计信息正确（平均评分、各类型分布）
- ✅ 标记处理、未处理查询正确
- ✅ 死锁问题已修复，查询不再卡死

---

#### ✅ P2-2: 版本管理与增量同步模块（version_manager.py）

**新建文件**：`services/data/version_manager.py`（新建 `services/data/` 目录）

**问题**：
- 每次全量重建向量库，成本很高
- PubMed/arXiv 每天都有新论文，不知道哪些是新的
- 没有版本记录，无法回滚或追溯

**核心功能**：
1. **数据源管理**：
   - 6种数据源类型：pubmed / pmc / openalex / arxiv / zotero / local
   - `register_source()`：注册或更新数据源
   - 每个数据源记录：current_version、last_sync_at、total_papers、last_sync_added/updated/failed
   - 配置：auto_sync（自动同步）、sync_interval_hours（同步间隔）、max_papers_per_sync
2. **同步任务管理**：
   - `create_sync_task()`：创建同步任务（自动检查是否已有运行中的任务）
   - `update_task_progress()`：更新进度（progress、current_step、processed、added、updated、failed）
   - `complete_task()`：完成任务（自动更新数据源版本和统计）
   - `fail_task()` / `cancel_task()`：失败/取消
   - 7种状态：idle / pending / running / paused / completed / failed / cancelled
   - 自动估算剩余时间（根据处理速率）
3. **增量同步辅助**：
   - `get_incremental_query_params()`：获取增量查询参数（since_timestamp、since_date、max_papers）
   - `should_auto_sync()`：检查是否应该自动同步
   - `get_due_auto_sync_sources()`：获取需要自动同步的数据源列表
4. **统计**：`get_stats()`：总数据源数、启用数、自动同步数、总任务数、运行/完成/失败数、总论文数、最近7天/30天新增、最近同步时间、下次计划同步
5. **持久化存储**：JSON 文件，线程安全，全局单例

**测试结果**：
- ✅ 注册数据源、创建任务、更新进度、完成任务全部通过
- ✅ 版本号递增正确（完成一次同步后 version 从 0 → 1）
- ✅ 论文统计正确（新增 45 篇后 total_papers = 45）
- ✅ 增量查询参数正确（incremental=True, since_timestamp 正确）
- ✅ 统计信息正确

---

#### ✅ P2-3: 影响范围评估与局部重算模块（impact_analyzer.py）

**新建文件**：`services/review/impact_analyzer.py`

**问题**：
- EvidenceCard 变更后，不知道哪些章节和综述受影响
- 只能全局重跑，浪费计算资源
- 没有变更影响报告，无法决定是否需要重算

**核心功能**：
1. **依赖关系图**：
   - EvidenceCard → 章节 → 综述 的完整依赖关系
   - `register_dependency()`：注册依赖（evidence_id、section_id、review_id、paper_id、章节元数据）
   - `unregister_dependency()`：注销依赖
   - 自动维护双向索引（evidence→sections、section→evidence、section→review、review→sections、paper→evidence）
2. **影响评估**：
   - `assess_impact()`：评估变更的影响范围
   - 支持通过 evidence_ids / paper_ids / section_ids / review_ids 评估
   - 12种变更类型：evidence_add/remove/update/merge/deprecate/conflict、paper_add/remove、outline_change、data_sync
   - 5级影响级别：none / low / medium / high / critical
   - 自动计算：受影响章节数、受影响章节详情（影响级别、受影响证据数、是否需要重算、预估重算时间）、受影响综述数、总体影响级别
3. **重算策略**：
   - 4种策略：auto（自动）、manual（手动）、threshold（阈值触发）、none（不重算）
   - 自动判断 should_recalc（影响达到 medium 及以上时建议重算）
   - 自动判断重算范围（partial 局部 / full 全量）
   - 自动估算总重算时间
4. **处理建议**：
   - 自动生成 recommendations（针对不同变更类型给出具体建议）
   - 证据冲突→建议人工复核；证据失效→建议替换；数据同步→建议评估更新
5. **局部重算管理**：
   - `mark_recalc_completed()`：标记重算完成（可指定哪些章节已重算）
   - `mark_recalc_skipped()`：标记跳过重算
   - `get_pending_reports()`：获取待处理的影响报告
6. **持久化存储**：JSON 文件，线程安全，全局单例

**测试结果**：
- ✅ 注册依赖关系正确
- ✅ 证据新增影响评估正确（level=high, should_recalc=True）
- ✅ 证据移除高影响评估正确
- ✅ 通过论文 ID 评估影响正确（影响 2 个章节、2 条证据）
- ✅ 标记重算完成正确
- ✅ 查询报告正确

---

#### ✅ P2-4: 统一错误处理与重试模块（retry_utils.py）

**新建文件**：`services/utils/retry_utils.py`（新建 `services/utils/` 目录）

**问题**：
- API 失败、解析失败、模型超时，没有统一的重试和降级机制
- LLM 调用失败时直接报错，没有备用模型
- 解析器失败时没有 fallback 链
- 多次失败的任务没有死信队列，丢失后无法重试

**核心功能**：
1. **@retry 装饰器**：
   - 指数退避重试（base_delay × backoff_factor^(attempt-1)）
   - 可配置：max_attempts、base_delay、max_delay、backoff_factor
   - 可指定 retryable_exceptions（只重试特定异常类型）
   - 支持 jitter（随机抖动，避免惊群效应）
   - 回调函数：on_retry / on_success / on_failure
2. **LLMRouter（LLM 调用重试+降级）**：
   - 注册主模型和多个备用模型（按优先级）
   - 策略：先调用主模型，失败后重试 max_retries_per_model 次，再依次尝试备用模型
   - 统计：总调用数、主模型成功数、降级使用数、总失败数
3. **ParserFallbackChain（解析器 fallback 链）**：
   - 按添加顺序依次尝试各解析器
   - Docling → GROBID → MinerU → pdfplumber
   - 返回 (result, parser_used_name)，知道最终用了哪个解析器
   - 统计：各解析器使用次数、fallback 次数
4. **DeadLetterQueue（死信队列）**：
   - 多次失败的任务进入死信队列，不丢失
   - `add_task()`：添加失败任务（记录 payload、error_message、attempt_count）
   - `retry_task()`：重试任务（传入 handler 函数，返回 True 表示成功）
   - `dismiss_task()`：驳回/忽略任务
   - `get_pending_tasks()`：获取待处理任务（可按类型过滤）
   - 4种状态：pending / retrying / resolved / dismissed
   - 持久化存储，全局单例
5. **错误统计**：总错误数、总重试数、重试后成功数、死信数、成功率、按错误类型/任务名统计

**测试结果**：
- ✅ @retry 装饰器正确（失败2次后第3次成功）
- ✅ LLMRouter 主模型重试成功正确
- ✅ LLMRouter 降级到备用模型正确
- ✅ ParserFallbackChain fallback 正确（parser1 失败后用 parser2）
- ✅ 死信队列添加、查询、重试、统计全部正确

---

#### ✅ P2-5: 结构化日志与监控模块（structured_logger.py）

**新建文件**：`services/utils/structured_logger.py`

**问题**：
- 日志格式不统一，难以分析和查询
- 没有监控指标，不知道系统运行状态
- 无法按条件查询历史日志
- 控制台输出和文件输出混在一起

**核心功能**：
1. **JSON 格式结构化日志**：
   - 每条日志包含：log_id、timestamp、level、module、event、message、details、duration_seconds、request_id、metadata
   - 5种级别：debug / info / warning / error / critical
   - 可配置 min_level（低于此级别的日志不记录）
2. **便捷方法**：
   - `debug()` / `info()` / `warning()` / `error()` / `critical()`
   - `error()` 和 `critical()` 支持传入 Exception 对象，自动记录 error_type 和 error_message
3. **计时器上下文管理器**：
   - `with logger.timer('event_name', details={...}):` 自动记录耗时
   - 异常时自动记录 error 级别日志（包含异常信息和耗时）
   - 成功时记录 info 级别日志（包含耗时）
4. **日志查询**：
   - `query(level, module, event, keyword, since_seconds, limit)`：多条件查询
   - `get_recent(n)`：获取最近 N 条
   - 支持关键词搜索（在 message 和 details 中搜索）
5. **监控指标**：
   - `get_stats()`：总请求数、总错误数、错误率、平均耗时、P50/P95/P99 耗时
   - 按模块/事件/级别统计调用次数
   - `reset_stats()`：重置统计
6. **日志文件轮转**：
   - 单个文件最大 50MB（可配置）
   - 最多保留 10 个文件（可配置）
   - 自动轮转（app.log → app_1.log → app_2.log ...）
7. **控制台输出**：
   - 带图标和颜色的控制台输出（🔍 debug / ✅ info / ⚠️ warning / ❌ error / 🔥 critical）
   - 可配置是否输出到控制台
8. **全局单例**：`get_logger(module)` 获取指定模块的日志记录器

**测试结果**：
- ✅ 各级别日志记录正确
- ✅ 计时器上下文管理器正确（自动记录耗时）
- ✅ 按级别/事件/关键词查询正确
- ✅ 监控统计正确（总请求数、错误率、平均耗时、P50/P95/P99）
- ✅ 日志级别过滤正确（min_level=warning 时 info 不记录）

---

#### ✅ P2-6: 导出与分享功能模块（export_manager.py）

**新建文件**：`services/review/export_manager.py`

**问题**：
- 生成的综述只能在网页端查看，无法导出
- 没有分享功能，无法分享给他人
- 导出格式单一，不支持学术常用格式

**核心功能**：
1. **多格式导出**：
   - **Markdown**：完整的 Markdown 格式，包含标题、章节、参考文献
   - **BibTeX**：参考文献导出为 .bib 文件，支持 LaTeX 引用
   - **JSON**：完整数据导出（包含所有元数据、证据、引用）
   - **纯文本**：纯文本格式，方便复制粘贴
   - （PDF / Word 格式预留接口，后续可接入对应库）
2. **导出配置**：
   - include_references：是否包含参考文献
   - include_evidence_ids：是否包含证据 ID（方便回查）
   - citation_style：引用格式（apa / nature / vancouver）
   - language：语言（en / zh）
3. **导出任务管理**：
   - `create_export()`：创建导出任务
   - `update_task_progress()`：更新进度
   - `complete_task()`：完成任务（保存文件）
   - `fail_task()`：标记失败
   - `list_tasks()`：列出任务（可按综述ID/状态过滤）
   - 4种状态：pending / processing / completed / failed
   - 文件自动过期（默认 72 小时）
4. **具体导出方法**：
   - `export_to_markdown()`：导出为 Markdown（自动生成标题、章节、参考文献）
   - `export_to_bibtex()`：导出为 BibTeX（自动生成 @article 条目）
   - `export_to_json()`：导出为 JSON（完整数据）
   - `export_to_plain_text()`：导出为纯文本
5. **分享链接**：
   - `create_share_link()`：创建分享链接
   - 安全设置：password（访问密码，可选）、expires_in_hours（过期时间）、max_views（最大访问次数）
   - `verify_share_link()`：验证分享链接（检查密码、过期、访问次数）
   - `revoke_share_link()`：撤销分享链接
   - `list_share_links()`：列出分享链接
   - 密码使用 SHA256 哈希存储，不明文保存
6. **统计**：
   - `get_stats()`：总导出数、按格式/状态统计、总文件大小、平均处理时间、总分享链接数、活跃分享链接数

**测试结果**：
- ✅ 创建导出任务正确
- ✅ Markdown 导出正确（包含标题、章节、参考文献，205 bytes）
- ✅ BibTeX 导出正确
- ✅ JSON 导出正确
- ✅ 查询任务正确（3 个任务）
- ✅ 创建分享链接正确（带密码）
- ✅ 验证分享链接正确（正确密码通过、错误密码拒绝、无密码提示需要密码）
- ✅ 撤销分享链接正确（撤销后验证失败）
- ✅ 统计信息正确

---

#### 📊 P2 优化效果总结

| 优化项 | 解决的问题 | 核心价值 | 新建文件 |
|--------|-----------|----------|----------|
| 用户反馈闭环 | 用户修改不回流，系统无法进化 | 记录用户修改，用于微调 reranker/prompt，自动生成改进建议 | `services/review/user_feedback.py` |
| 版本管理与增量同步 | 每次全量重建，成本高 | last_sync 时间戳，增量拉取，向量库 upsert，定时同步 | `services/data/version_manager.py` |
| 影响范围评估+局部重算 | 只能全局重跑，浪费资源 | 自动评估受影响章节，只重算受影响部分，变更影响报告 | `services/review/impact_analyzer.py` |
| 错误处理与重试 | 失败直接报错，无降级 | 统一重试装饰器，LLM降级，解析器fallback链，死信队列 | `services/utils/retry_utils.py` |
| 结构化日志与监控 | 日志不统一，无监控 | JSON结构化日志，多条件查询，P50/P95/P99监控指标 | `services/utils/structured_logger.py` |
| 导出与分享功能 | 只能网页查看，无法分享 | Markdown/BibTeX/JSON/纯文本导出，带密码的分享链接 | `services/review/export_manager.py` |

---

#### 📈 P0+P1+P2 完整优化清单（全部完成）

**P0（核心链路补强）—— 3项，全部完成 ✅**
1. EvidenceCard 去重与置信度（models.py + evidence_extractor.py）
2. 证据不足时的 fallback 机制（review_generator.py）
3. 同步更新文档脚本

**P1（支撑链路核心）—— 3项，全部完成 ✅**
1. 检索可观测性（retrieval_observability.py）
2. 句子关系判定（sentence_relation_classifier.py）
3. EvidenceCard 增量维护（evidence_card_incremental_manager.py）

**P2（支撑链路完善）—— 6项，全部完成 ✅**
1. 用户反馈闭环（user_feedback.py）
2. 版本管理与增量同步（version_manager.py）
3. 影响范围评估+局部重算（impact_analyzer.py）
4. 错误处理与重试（retry_utils.py）
5. 结构化日志与监控（structured_logger.py）
6. 导出与分享功能（export_manager.py）

**总计：12 项优化，全部完成并通过功能测试！**

---

#### 🎯 后续计划

1. **将 P0/P1/P2 的新模块接入主程序**（api_server.py + review_generator.py）
   - 检索时自动记录到 retrieval_observability
   - 生成时自动记录到 structured_logger
   - LLM 调用使用 LLMRouter 重试+降级
   - 导出功能接入前端
2. **前端集成**：
   - 检索可观测性面板（展示每次检索的各路召回、重排、耗时）
   - 导出按钮（Markdown/BibTeX/JSON）
   - 分享按钮（生成带密码的分享链接）
   - 用户反馈入口（评分、评论、修改记录）
3. **增量同步自动化**：
   - 定时任务自动同步 PubMed/PMC 新论文
   - 自动增量建索引（不重建）
   - 自动评估影响范围，提示用户是否需要重算综述
4. **代码提交推送**：将 V33.4/V33.5/V33.6 的所有修改提交到 Gitee

---

#### ⚠️ 核心原则（继续保持）

1. **检索层不改，只改数据层**——只更新向量库，主程序搜索逻辑一行都不用改
2. **综述生成不需要关系抽取和冲突检测**——这些是问答/分析功能用的
3. **证据锚定生成**——任何结论，没有 EvidenceCard 就禁止写入综述正文
4. **证据不足时降级，不硬编**——明确标注"直接证据有限"，避免幻觉
5. **不重建，只追加 + 标记**——旧数据不动，新数据挂上去，冲突用标记不用删除
6. **EvidenceCard 是增量单位**——不是论文，不是句子，而是 EvidenceCard
7. **P0/P1/P2 都是支撑链路，不改变核心逻辑**——核心检索和生成逻辑保持稳定
8. **新模块都是全局单例，线程安全**——支持并发访问，不阻塞主流程

---

## 📅 2026-10-10

### 🧪 新增：实验方法（Protocol）专项批量下载脚本

**文件**：`download_protocols.py`（V1.0，约700行）

#### 背景

调研发现实验方法（Protocols）有多个专门数据库：
- **Bio-protocol**（5,500+，完全OA，PMC收录，斯坦福2011年创立）
- **STAR Protocols**（Cell Press，OA，PMC收录）
- **Nature Protocols**（部分OA）
- **Methods in Molecular Biology**（Humana Press，部分OA）
- **Cold Spring Harbor Protocols**（部分OA）
- **JoVE**（视频实验期刊，部分OA）
- **protocols.io**（111,900+，有公开API v3，2023年被Springer Nature收购）

按照核心原则——**只加数据层，不改检索层**，Protocol文章下载后走同样的解析→建库→建向量索引流程，主程序一行代码都不用改。

#### 功能特性

1. **6种Protocol专刊支持**：bio-protocol / star-protocols / nature-protocols / methods-mol-biol / csh-protocols / jove
2. **两种搜索模式**：
   - 特定期刊筛选（`--journal bio-protocol`）
   - 通用搜索（主题 + protocols/methods关键词 + free full text过滤）
3. **批量主题下载**（`--batch`）：内置8大分类60+主题
   - 分子生物学、细胞生物学、基因组学、蛋白质组学
   - 免疫学、生物信息学、肿瘤研究、神经科学
4. **摘要+全文双下载**：
   - 摘要保存为JSON（`abstracts_protocols/`）
   - PMC全文XML（`documents_protocols/`）
5. **自动过滤只有摘要的文章**（检查`<body>`标签）
6. **增量下载**（已下载的自动跳过）
7. **NCBI速率限制**（有API Key 0.12秒/请求，无Key 0.35秒/请求）
8. **重试机制**（3次重试，指数退避）
9. **Windows编码修复**（强制utf-8，避免cp1252崩溃）

#### 使用方法

```bash
# 按主题搜索下载所有类型protocol（默认100篇）
python download_protocols.py --query "single cell RNA sequencing"

# 只下载 Bio-protocol 期刊的
python download_protocols.py --query "flow cytometry" --journal bio-protocol

# 批量下载内置主题（8大分类60+主题）
python download_protocols.py --batch

# 批量下载指定分类
python download_protocols.py --batch-cat "基因组学,蛋白质组学" --max 50

# 只下载摘要，不下载XML
python download_protocols.py --query "PCR" --no-xml

# 只搜索不下载（预览）
python download_protocols.py --query "ChIP-seq" --dry-run
```

#### 测试结果

- ✅ 语法检查通过
- ✅ 通用搜索正常（single cell RNA sequencing → 20篇）
- ✅ 特定期刊搜索正常（Bio-protocol + flow cytometry → 10篇）
- ✅ 完整流程测试通过（western blot + Bio-protocol → 5篇摘要，2篇XML全文，3篇只有摘要被过滤，0失败）
- ✅ 摘要JSON格式正确（包含pmid/pmcid/doi/title/authors/journal/abstract等字段）
- ✅ XML全文下载正确（JATS格式，有`<body>`标签）

#### 关键技术点

1. **PubMed搜索语法修正**：
   - ❌ `protocol[Publication Type]` —— PubMed没有这个Publication Type，搜不到
   - ❌ `"open access"[Filter]` —— 不是正确的filter语法
   - ✅ `free full text[Filter]` —— 正确的免费全文过滤
   - ✅ `"protocols"[Title/Abstract] OR "method"[Title/Abstract]` —— 通用protocol筛选

2. **全文过滤**：下载XML后检查是否有`<body>`标签，只有摘要的文章自动删除

3. **输出目录分离**：Protocol数据单独存放在`abstracts_protocols/`和`documents_protocols/`，不跟普通论文混在一起

#### 后续工作

1. 将Protocol数据导入现有建库流程（import_xml.py + build_vector_index.py）
2. 考虑是否需要单独建一个protocol分类的向量库collection
3. protocols.io API对接（有公开API v3，可拉取111,900+方法）
4. 前端增加"实验方法"分类筛选

---

#### ⚠️ 核心原则（继续保持）

1. **检索层不改，只改数据层**——只更新向量库，主程序搜索逻辑一行都不用改
2. **综述生成不需要关系抽取和冲突检测**——这些是问答/分析功能用的
3. **证据锚定生成**——任何结论，没有 EvidenceCard 就禁止写入综述正文
4. **证据不足时降级，不硬编**——明确标注"直接证据有限"，避免幻觉
5. **不重建，只追加 + 标记**——旧数据不动，新数据挂上去，冲突用标记不用删除
6. **EvidenceCard 是增量单位**——不是论文，不是句子，而是 EvidenceCard
7. **P0/P1/P2 都是支撑链路，不改变核心逻辑**——核心检索和生成逻辑保持稳定
8. **新模块都是全局单例，线程安全**——支持并发访问，不阻塞主流程
9. **数据层扩展遵循统一流程**——新数据源（Protocol/arXiv/Zotero）都走 下载→解析→建库→建向量索引 四步，检索层零改动

---

## V33.8 — 生物信息学方法（Workflow/Pipeline/Tool）开放API对接 + 调研文档（2026-10-10）

### 背景

在完成湿实验 Protocol（protocols.io/Bio-protocol/PMC）专项下载脚本（V33.7）后，用户进一步要求调研**生物信息学分析方法**类的开放数据库。生物信息学方法（Workflow/Pipeline/Tool）具有高度结构化的特点（机器可读的工作流描述、明确的软件版本和依赖、精确的参数说明、容器化保证可复现），比普通论文中的 Methods 部分更精确、更适合建库。

### 完成内容

#### 1. 新建 `download_bioinformatics_methods.py`（V1.0，约600行）

对接三个开放API平台，批量下载结构化的生物信息学方法元数据：

| 平台 | API类型 | 规模 | 下载类 |
|------|---------|------|--------|
| **Dockstore** | GA4GH TRS v2 标准REST API | 数万workflow+tool | `DockstoreDownloader` |
| **bio.tools** | Django REST API（ELIXIR支持） | 34,459+工具/数据服务 | `BioToolsDownloader` |
| **nf-core** | GitHub API | 62个curated pipeline（33发布+24开发+5归档） | `NFCoreDownloader` |

**功能特性**：
- 三个平台统一接口，支持 `--source {all,dockstore,biotools,nfcore}` 选择
- 支持12个主题筛选（genomics/transcriptomics/proteomics/metabolomics/epigenomics/single_cell/metagenomics/structural_biology/phylogenetics/machine_learning/visualization/statistics）
- 增量下载、自动限速、错误重试
- nf-core 自动获取每个pipeline的README文档（增加方法描述内容）
- 输出结构化JSON，包含名称、描述、标签、作者、许可证、参数、输入输出、链接等
- 下载清单自动保存（`download_manifest.json`）
- Windows控制台编码兼容

**使用方法**：
```bash
# 下载所有来源（默认各100条）
python download_bioinformatics_methods.py

# 只下载Dockstore
python download_bioinformatics_methods.py --source dockstore

# 每个来源下载500条
python download_bioinformatics_methods.py --max 500

# 按基因组学主题筛选
python download_bioinformatics_methods.py --topic genomics

# 预览模式
python download_bioinformatics_methods.py --dry-run
```

#### 2. 新建《生物信息学方法数据库调研与建库指南.md》

完整的调研文档，包含：
- 10+个开放数据库的详细汇总（规模、开放获取状态、API、数据格式、特点）
- 第一梯队：Dockstore、WorkflowHub、nf-core、Snakemake Catalog、Galaxy IWC
- 第二梯队：bio.tools、Galaxy ToolShed、Bioconda、BioContainers
- 中国资源：国家生物信息中心（CNCB/NGDC）
- 建库方案设计（优先级、数据处理流程、核心原则、与湿实验Protocol的互补关系）
- 后续扩展方向（短期/中期/长期）
- 完整的API使用示例和参考链接

### 测试验证

- ✅ 语法检查通过
- ✅ `--help` 正常显示
- ✅ bio.tools API测试：获取到34,459个工具总数，成功下载50条，工具类型和主题统计正常
- ✅ Dockstore API测试：成功下载10条workflow
- ✅ nf-core API测试：GitHub限流等待后成功获取8个pipeline，README获取正常，主要语言Nextflow/Python
- ✅ 三个来源全部独立测试通过

### 关键技术点

1. **Dockstore GA4GH TRS API**：
   - 端点：`https://dockstore.org/api/ga4gh/trs/v2/tools`
   - 支持 `type=workflow` 筛选，`limit`/`offset` 分页
   - workflow_id 需要URL编码（如 `#workflow/github.com/nf-core/rnaseq`）

2. **bio.tools API**：
   - 端点：`https://bio.tools/api/t/`
   - 支持 `page`/`page_size` 分页，`topic`/`toolType` 筛选
   - 响应格式：`{count, next, previous, list[]}`
   - EDAM本体分类，元数据丰富（主题、操作、数据类型、格式、许可证）

3. **nf-core GitHub API**：
   - 端点：`https://api.github.com/orgs/nf-core/repos`
   - 支持 `sort=updated`、`type=public`、`per_page` 分页
   - 注意GitHub API限流（未认证60次/小时），限流时等待60秒重试
   - 排除非pipeline仓库（modules/tools/website/configs等）
   - 通过README API获取每个pipeline的文档内容

4. **输出目录分离**：生物信息学方法数据单独存放在 `bioinformatics_methods/` 下，按来源分子目录（dockstore/biotools/nfcore）

### 同步更新

- ✅ WORK_LOG.md 追加 V33.8 完整记录
- ✅ test_workflow.sh 增加阶段3.8（生物信息学方法下载脚本测试，6项）
- ✅ self_check.py 增加检查6.6（生物信息学方法下载脚本检查，约20项），版本号更新为V33.8
- ✅ Gitee 提交推送

### 核心原则（继续保持）

1. **检索层不改，只改数据层**——生物信息学方法数据走现有 下载→解析→建库→建向量索引 四步，检索层零改动
2. **向量库是主程序的数据源**——往里加数据就行，搜索逻辑不用变
3. **Embedding模型一致**——用跟老库一样的bge-base-en-v1.5，保证向量空间一致
4. **湿实验Protocol + 生信Workflow互补建库**——合在一起就是完整的"从实验到分析"全流程方法库

### 后续工作

1. 将生物信息学方法数据导入现有建库流程（解析JSON→提取文本→建向量索引）
2. WorkflowHub API对接（与Dockstore互补，欧洲ELIXIR支持）
3. Galaxy ToolShed API对接（数千工具XML wrapper）
4. Bioconda/BioContainers元数据对接
5. 元数据增强（提取EDAM本体分类、工具类型、输入输出格式等结构化字段）
6. 方法-论文关联（将生信方法与引用该方法的论文关联）
7. 前端增加"分析方法"分类筛选

---

## V33.9 — LLM 模型配置优化：7b Q4 量化版适配 8GB 显存（2026-10-11）

### 背景

用户显卡为 RTX 4060 8GB。原配置中重量模型为 `qwen2.5:7b`（FP16，~8GB显存），加上常驻的 Embedding（~1.5GB）和 Reranker（~1.2GB），总显存需求 ~10.7GB，**8GB 显存装不下**，会导致 OOM 或回退 CPU 运行。

### 修改内容

将重量模型默认值从 `qwen2.5:7b`（FP16）改为 `qwen2.5:7b-instruct-q4_K_M`（Q4量化）：

| 模型 | 精度 | 显存需求 | 常驻+LLM合计 | 8GB显存 |
|------|------|---------|-------------|---------|
| qwen2.5:7b | FP16 | ~8GB | ~10.7GB | ❌ 爆显存 |
| qwen2.5:7b-instruct-q4_K_M | Q4量化 | ~4.5GB | ~7.2GB | ✅ 可跑 |

量化版质量与 FP16 差距在 3-5% 以内，几乎感知不到，但显存省一半。

### 修改的文件

1. **services/review/llm_client.py**
   - 文档注释：默认模型改为 `qwen2.5:7b-instruct-q4_K_M`
   - `create_llm_client()` 函数：heavy model 默认值从 `qwen2.5:7b` 改为 `qwen2.5:7b-instruct-q4_K_M`
   - 轻量模型保持 `qwen2.5:3b` 不变（生成大纲，速度优先）

2. **services/review/review_generator.py**
   - 注释更新：轻量模型默认值说明从 `qwen2.5:7b` 修正为 `qwen2.5:3b`
   - 增加 V33.9 量化版说明

3. **services/qa/qa_service.py**
   - Ollama 本地模式默认模型从 `qwen2.5:14b` 改为 `qwen2.5:7b-instruct-q4_K_M`

4. **.env.example**
   - 增加 Ollama 本地配置示例（含量化版模型名）

### 用户需要执行的操作

```bash
# 1. 下载 7b Q4_K_M 量化版模型
ollama pull qwen2.5:7b-instruct-q4_K_M

# 2. （可选）删掉原来的 FP16 版 7b，节省磁盘空间
ollama rm qwen2.5:7b

# 3. 重启 api_server.py 即可生效
```

### 显存账本（优化后）

| 模块 | 显存占用 |
|------|---------|
| bge-base-en-v1.5 (Embedding) | ~1.5GB |
| bge-reranker-base (重排) | ~1.2GB |
| qwen2.5:7b-instruct-q4_K_M (LLM) | ~4.5GB |
| **合计** | **~7.2GB / 8GB** |

剩余 ~0.8GB 余量，安全。如果后续做 Embedding/Reranker 按需加载，还能再省 2.7GB 给 LLM。

### 核心原则

- 轻量任务（生成大纲、证据抽取）用 3b，速度快
- 重量任务（写综述正文、问答）用 7b Q4，质量好
- 两个模型分时复用，不会同时加载，Ollama 自动管理显存

---

## V33.10 — Protocols.io API 对接：实验方法实时搜索（2026-10-11）

### 背景

用户提出关键架构洞察："网上做的 Protocol 本身做得挺好的，我们是不是可以直接拿来用，而不是再造轮子嵌入到系统里？"

经调研确认：
- **protocols.io** 已有完整 REST API v3 + 官方 MCP Server + Advanced AI 功能
- 25k+ 公开协议，结构化数据（步骤/试剂/材料/时间字段化）
- 被 Springer Nature 收购，持续维护
- 完全不需要下载数据建库，直接 API 实时调用

### 核心原则

**能对接的就对接，必须自建的才自建。** 不重复造轮子。

三层混合架构：
1. **直接对接**（不下载，实时调用）：protocols.io API
2. **API实时检索**（不建向量库，调对方搜索API）：Dockstore/bio.tools/nf-core/NCBI
3. **本地建库**（下载→解析→建向量索引）：PubMed摘要/PMC全文/Bio-protocol(via PMC)

### 修改内容

#### 1. 新建 `services/search/protocols_io_client.py`（V1.0，约500行）

Protocols.io API 客户端，功能：
- `ProtocolsIOResult` 类：统一格式的搜索结果（跟论文格式兼容）
- `ProtocolsIOClient` 类：API 客户端
  - `search()` — 搜索公开协议（支持关键词、排序、分页）
  - `get_protocol()` — 获取协议详情（含完整步骤/试剂）
  - `search_and_format()` — 搜索并返回字典列表（混合检索直接用）
  - 内置缓存（7天有效）、限速（0.5秒/请求）、重试（3次）
- 便捷函数：`search_protocols_io()`、`is_protocols_io_available()`
- 命令行测试入口：`python protocols_io_client.py "western blot" 5`
- Windows 控制台编码兼容

API 端点：
- 搜索：`GET /protocols?filter=public&key=<query>&page_size=<n>&order_field=activity`
- 详情：`GET /protocols/<id>`
- 认证：`Authorization: Bearer <ACCESS_TOKEN>`

#### 2. 修改 `services/search/hybrid_retriever.py`（V1.0 → V1.1）

集成 Protocols.io 为第三个搜索源：
- `__init__` 增加 `use_protocols_io`、`protocols_io_max_results` 参数
- 新增 `_search_protocols_io()` 方法
- `search_papers()` 增加 `use_protocols_io`、`protocols_io_max_results` 参数
- 三路并行搜索（本地 + 在线NCBI + Protocols.io），ThreadPoolExecutor max_workers=3
- 返回结果增加 `protocols` 和 `protocols_count` 字段
- **论文检索接口完全不变**（向后兼容），Protocols.io 结果独立返回，不与论文混合去重

### 用户需要做的配置

```bash
# 1. 注册 protocols.io 账号
#    https://www.protocols.io

# 2. 在 Settings → API 中创建 Client Access Token

# 3. 设置环境变量（Windows PowerShell）
$env:SCIPAL_PROTOCOLS_IO_TOKEN="your_token_here"

# 4. 重启 api_server.py 即可生效
#    未设置 token 时自动跳过，不影响现有功能
```

### 设计决策

1. **Protocols.io 结果独立返回，不与论文混合** — 实验方法跟论文是不同类型内容，分开更清晰，前端可以分别展示"论文"和"实验方法"标签页
2. **不下载数据，不建向量库** — protocols.io 自己有搜索和AI，直接调API，零存储成本
3. **检索层接口不变** — 论文搜索的返回格式完全不变，只是多了一个 `protocols` 字段，旧代码不受影响
4. **可选启用** — 没配置 token 时自动跳过，不影响现有功能

### 显存/资源影响

- **0MB 显存增加** — 纯 API 调用，不加载任何 AI 模型
- **~50MB 内存增加** — 客户端实例 + 缓存
- 完全不影响 RTX 4060 8GB 的显存分配

### 后续可扩展

- 前端搜索页增加"实验方法"标签页，展示 protocols.io 结果
- 综述生成时自动检索相关实验方法作为补充材料
- 实验设计功能直接调用 protocols.io 搜索 + 详情
- 对接 protocols.io MCP Server（如果后续用 MCP 框架）
