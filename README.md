# Sci-Pal — 科研文献 RAG 助手

基于本地 PDF 的学术文献检索与问答系统。核心是**确定性检索层**（向量 + FTS5 + RRF 融合 + Cross-Encoder Rerank + 查询路由 + 小→大扩展 + 多查询 + 数据质量治理），生成式 LLM 为可选表达层。

> 当前版本：**V25.9** · 94 篇论文 · 16036 段落 · 双Provider（本地Ollama + 云端API）· 大纲可视化编辑器 · 英文综述生成

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    表达层（可选 LLM）                      │
│   证据卡片 → 自然语言总结 / 解释 / 对比 / 综述             │
│   （挂了不影响检索，强制基于编号信封、带引用）              │
├─────────────────────────────────────────────────────────┤
│                    服务层（Flask API）                     │
│  /api/retrieve · /api/papers · /api/agentic/search        │
│  /api/communities · /api/graph/stats · PDF 服务            │
│  前端：搜索页 + PDF.js 阅读器 + 双栏对比                    │
├─────────────────────────────────────────────────────────┤
│                    检索层（核心，确定性）                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ 查询路由   │ │ 多查询    │ │ 混合检索   │ │ Rerank    │ │
│  │ QueryRouter│ │ HyDE     │ │ Vector+FTS│ │ CrossEnc  │ │
│  └──────────┘ └──────────┘ └────┬─────┘ └─────┬─────┘ │
│       │               │          RRF 融合         │       │
│       ▼               ▼                           ▼       │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  小→大扩展 + 800token 分块 + 元数据过滤              │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ 图谱遍历   │ │ Agentic  │ │ 社区检测   │ │ 数据质量   │ │
│  │ Graph     │ │ 多跳检索  │ │ Leiden    │ │ 治理       │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
├─────────────────────────────────────────────────────────┤
│                    数据层（离线构建）                       │
│  Docling（正文/图表/章节/坐标）+ GROBID（元数据/参考文献）│
│  → SQLite（papers/paragraphs/figures/tables/citations/   │
│           chunks/paper_communities/community_members）     │
│  → Chroma（paragraphs/papers/figures/tables/chunks）      │
│  → FTS5（paragraphs_fts / papers_fts 全文索引）           │
│  → 图谱：DESCRIBED_IN / CITES / SIMILAR 边               │
└─────────────────────────────────────────────────────────┘
```

### 两层解耦设计

| | 核心层（确定性检索） | 表达层（可选 LLM） |
|---|---|---|
| **职责** | 检索、定位、图谱、证据卡片 | 把证据综合成自然语言 |
| **特性** | 离线、可溯源、零幻觉 | 基于编号信封、带引用、覆盖率不足重试 |
| **依赖** | sentence-transformers + CrossEncoder（本地小模型） | 任意生成式 LLM（可选） |
| **挂了** | — | 不影响检索，降级为"证据模式" |

---

## 目录结构

```
sciPal/
├── api_server.py              # V24.3 Flask API 入口（推荐）
├── app.py                     # 旧版 v0.6.0 入口（保留兼容）
├── requirements.txt           # Python 依赖
├── VERSION                    # 版本号唯一真相源
├── README.md                  # 本文件
├── WORKLOG.md                 # 开发日志（V0–V24.3）
│
├── build_db/                  # 离线建库（GPU 机器上运行）
│   ├── build_database.py      #   主建库脚本（Docling + GROBID → SQLite）
│   ├── build_embeddings.py    #   构建 Chroma 向量索引
│   ├── build_fts.py           #   构建 FTS5 全文索引
│   ├── build_figure_links.py  #   V22.2 图表→正文 DESCRIBED_IN 绑定
│   ├── build_paper_graph.py   #   V22.3 论文引用+相似性图谱
│   ├── build_chunks.py        #   V24.1 800token 章节感知分块
│   ├── build_communities.py   #   V24.3 Leiden/Louvain 社区检测+摘要
│   ├── dedup_papers.py        #   V21.6 重复论文去重
│   ├── match_captions_to_figures.py  # 图注与图片空间匹配
│   ├── resolve_ref_dois.py    #   参考文献 DOI 解析
│   └── parsers/               #   Docling / GROBID 解析器
│
├── services/search/           # 检索层（核心）
│   ├── hybrid_search.py       #   混合检索（向量 + FTS + RRF + 多查询 + 分块 + 过滤）
│   ├── reranker.py            #   Cross-Encoder Rerank
│   ├── query_router.py        #   查询路由（qa/citation/figure/method）
│   ├── context_expander.py    #   小→大扩展（段落→整节）
│   ├── unified_retriever.py   #   统一检索信封（所有模块的入口）
│   ├── query_expander.py      #   V22.1 多查询/HyDE
│   ├── reference_filter.py    #   V21.7 参考文献条目过滤
│   ├── boilerplate_filter.py  #   V21.8 boilerplate 行级清洗
│   ├── graph_traverser.py     #   V23.1 图谱遍历（CITES/SIMILAR 边扩展）
│   ├── agentic_search.py      #   V23.2 Agentic 多跳检索
│   └── chunker.py             #   V24.1 800token 章节感知贪心装箱分块
│
├── services/query/            # 旧版基础查询服务（v0.6.0）
├── routes/                    # 旧版 Flask Blueprint（v0.6.0）
├── frontend/                  # 前端（搜索页 + PDF.js 阅读器 + 双栏对比）
│   ├── index.html             #   搜索主页
│   ├── viewer.html            #   V23.3 PDF.js 阅读器
│   └── compare.html           #   V23.3 双栏论文对比
├── scripts/                   # 测试与自检脚本
│   ├── run_tests.sh           #   全模块测试工作流
│   └── self_check.py          #   数据库+检索+数据质量自检
│
├── data/
│   ├── research.db            # SQLite 主数据库
│   └── chroma/                # Chroma 向量数据库
├── documents/                 # 原始 PDF
└── images/                    # 提取的图表图片
```

---

## 环境要求

- **Python** 3.11+（开发用 3.13.9）
- **依赖**：
  ```bash
  pip install flask sentence-transformers chromadb sqlite3 docling
  pip install grobid-client  # 可选，GROBID 需 Docker
  ```
- **GROBID**：Docker 容器（`grobid/grobid:0.9.1-full`，端口 8070），建库前需启动
- **模型**（首次运行自动下载，建议配置国内镜像）：
  - Embedding：`sentence-transformers/all-mpnet-base-v2`（768 维）
  - Reranker：`BAAI/bge-reranker-base`（约 1.11GB）
  ```bash
  export HF_ENDPOINT=https://hf-mirror.com
  ```
- **磁盘**：94 篇论文约需 2GB（含 PDF、提取图片、向量索引）

---

## 快速开始

### 1. 建库（离线，GPU 机器）

```bash
# 启动 GROBID
docker run -d --name grobid -p 8070:8070 grobid/grobid:0.9.1-full

# 解析 PDF → SQLite
python -m build_db.build_database

# 构建向量索引
python -m build_db.build_embeddings

# 构建 FTS5 全文索引
python -m build_db.build_fts
```

### 2. 数据质量治理（建库后必跑）

```bash
# 去重（先 dry-run 确认，再 --apply）
python -m build_db.dedup_papers
python -m build_db.dedup_papers --apply --vacuum

# 图表编号修正 + DESCRIBED_IN 边
python -m build_db.build_figure_links
python -m build_db.build_figure_links --apply

# 论文图谱（CITES + SIMILAR）
python -m build_db.build_paper_graph
python -m build_db.build_paper_graph --apply
```

### 3. 检索测试

```bash
# 统一检索（信封输出）
python -m services.search.unified_retriever

# 各模块单独测试
python -m services.search.query_expander     # 多查询变体
python -m services.search.query_router        # 查询路由
python -m services.search.hybrid_search       # 混合检索
python -m services.search.reranker            # Rerank
python -m services.search.reference_filter    # 参考文献过滤审计
python -m services.search.boilerplate_filter  # boilerplate 清洗审计
```

### 4. 启动 API + 前端

```bash
pip install flask
python api_server.py
# 打开 http://localhost:5000
```

---

## 检索层详解

### 混合检索（hybrid_search.py）

- **向量召回**：Chroma `paragraphs` 集合，cosine 相似度，top-20
- **FTS5 召回**：SQLite `paragraphs_fts`，BM25 排序，top-20
- **RRF 融合**：Reciprocal Rank Fusion（K=60），两通道结果合并
- **多查询**（V22.1）：QueryExpander 生成 2-4 个查询变体，所有变体 × 2 通道 RRF 合并，同一段落被多变体命中分数叠加
- **HyDE**（可选）：传入 LLM 生成函数时生成假设答案段落用于向量检索；无 LLM 时自动跳过

### Rerank（reranker.py）

- Cross-Encoder `BAAI/bge-reranker-base`，对 RRF 融合后的候选池（max(top_k×4, 20)）重排序
- 输出最终 top-k 结果

### 查询路由（query_router.py）

- 规则式路由，根据查询意图选择检索通道：
  - `qa`：段落检索（默认）
  - `citation`：参考文献检索
  - `figure`：图表检索
  - `method`：方法/实验检索
  - `papers`：跨论文发现
- 8/8 测试用例通过

### 小→大扩展（context_expander.py）

- 检索精准到段落（小 chunk），返回时按 `(paper_id, section_level1)` 分组拉取整节
- 章节超过 12 段退化为命中点前后窗口（前 3 + 后 3）
- 命中段用 `►...◄` 包裹，同父块合并、父块分数取最高命中分
- 信封默认渲染扩展版

### 数据质量治理

| 模块 | 版本 | 作用 |
|------|------|------|
| dedup_papers.py | V21.6 | 按 DOI + 归一化标题去重，98→94 篇 |
| reference_filter.py | V21.7 | 参考文献条目过滤（章节名 + 内容特征双重判定），38.6% 段落被标记 |
| boilerplate_filter.py | V21.8 | 首页 boilerplate 行级清洗（编辑信息/DOI/版权/作者单位/邮箱等 20+ 模式） |

### 图谱

| 边类型 | 版本 | 存储表 | 说明 |
|--------|------|--------|------|
| DESCRIBED_IN | V22.2 | paper_index | 段落 → 图表（正文引用 "Figure 3" 绑定到对应图） |
| CITES | V22.3 | cross_paper_index | 论文 → 论文（DOI 匹配 0.95 + 标题匹配 0.70） |
| SIMILAR | V22.3 | cross_paper_index | 论文 ↔ 论文（摘要向量余弦 >0.5，双向存储） |

---

## 综述 Agent 层详解（V25.x）

综述生成是 Sci-Pal 的核心能力，采用"证据卡片 → 关系图谱 → 冲突识别 → 大纲 → 撰写 → 逐句校验"的流水线，确保每句话都有文献来源支撑。

### 流水线概览

```
检索段落 → 证据抽取(EvidenceCard) → 关系抽取(Relation) → 冲突识别(Conflict)
                                                          ↓
                                              大纲生成 → 撰写 → 逐句校验 → 最终综述
```

### 证据卡片（EvidenceCard）

每条证据是综述的最小可信单元，强制绑定 `paper_id + para_id`，可反向溯源到 PDF 原文。

**V25.5 细粒度条件标签**：每条证据都会尽可能提取以下实验条件信息（原文没提则标记为"未知"）：

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `mutation_type` | 突变类型 | GOF（功能获得）/ LOF（功能丧失）/ 特定位点突变 / 不适用（正常生理） |
| `cell_type` | 细胞/样本类型 | 单核细胞 / T细胞 / 成纤维细胞 / 细胞系名称 / 小鼠模型 / 人类患者 |
| `measurement` | 测量指标 | mRNA水平 / 总蛋白水平 / 磷酸化蛋白水平 / DNA结合活性 / 功能实验 / 临床表型 |
| `stimulus` | 刺激条件 | IFN-α刺激 / IFN-gamma刺激 / IL-27刺激 / 病毒感染 / 未刺激（基线） |

这些条件标签是冲突识别中区分"真正矛盾"和"条件差异型"的基础。

### 关系抽取（RelationExtractor）

对所有证据对，用 LLM 判定逻辑关系：
- **supports（支持）**：一条证据的结论被另一条佐证
- **contradicts（矛盾）**：两条证据结论不一致
- **elaborates（展开）**：一条证据对另一条做更详细的解释或补充
- **unrelated（无关）**：讨论不同问题

**性能优化**：关键词粗筛（无共同关键词直接标 unrelated）+ 同论文内证据默认 elaborates + 批量 LLM 判定，可减少 50%+ 的 API 调用。

### 冲突识别与伪争议处理（V25.5 核心设计）

这是综述生成中最容易被误解的模块，需要重点说明。

#### 为什么会有"伪争议"？

学术文献中，不同研究在不同实验条件下得出不同结果是**非常正常的现象**，但简单的"看到反义词就判矛盾"的逻辑会把这些误判为"争议"。典型的伪争议包括：

| 伪争议类型 | 例子 | 为什么不是真矛盾 |
|-----------|------|-----------------|
| **突变类型不同** | "GOF突变中磷酸化增加" vs "LOF缺陷患者磷酸化受损" | GOF和LOF本来就应该结果相反，这是不同突变类型的正常差异 |
| **测量指标不同** | "mRNA水平正常" vs "蛋白水平降低" | mRNA和蛋白是不同维度，转录后调控可能导致两者不一致 |
| **生理 vs 病理** | "正常人STAT1高表达" vs "患者STAT1表达受损" | 一个是正常生理状态，一个是疾病状态，疾病导致表达变化是预期的 |
| **细胞类型不同** | "T细胞中表达高" vs "B细胞中表达低" | 不同细胞类型的基因表达本来就可能不同 |
| **刺激条件不同** | "未刺激时基线水平低" vs "IFN刺激后磷酸化升高" | 刺激前后结果不同是信号通路激活的正常表现 |

#### V25.5 的解决方案：分类呈现，不强制过滤

早期方案是"检测到条件差异就把矛盾降级掉"，但这样会**丢失有价值的学术信息**——不同条件下的不同结果本身就是重要的知识。

V25.5 采用**分类呈现**策略：保留所有信息，但分成两个章节，用不同的语气和结构呈现。

#### 综述中的两个章节

**章节1：研究争议与不一致**（真正矛盾）
- 判定标准：两条证据的**突变类型、测量指标、细胞类型、刺激条件都相同或高度相似**，但结论相反
- 语气：使用"争议""不一致""各方观点""需进一步验证"等词汇
- 结构：争议主题 → 争议小结 → 实验条件差异分析 → 各方观点列表
- 意义：这才是真正需要学术界进一步研究来解决的问题

**章节2：不同实验条件下的结果差异**（条件差异型）
- 判定标准：两条证据结论相反，但**关键实验条件明显不同**（由后处理规则自动检测 + LLM 判定双重保障）
- 开头明确说明："以下结果差异主要源于实验条件的不同（如突变类型、细胞类型、测量指标、刺激条件等），并非真正的学术争议。"
- 语气：客观陈述，不使用"争议""矛盾"等词汇
- 结构：差异主题 → 客观陈述（"在A条件下观察到X，在B条件下观察到Y"）→ 条件差异分析 → 各条件下的结果列表
- 意义：帮助读者理解"结果不同是因为条件不同"，而不是误以为文献间存在不可调和的矛盾

#### 自动检测的条件差异规则

后处理规则 `_check_condition_incomparability()` 会自动检测以下明显不可比的情况：

1. **GOF vs LOF**：一个是功能获得性突变，一个是功能丧失性突变/敲除/缺陷
2. **正常生理 vs 突变/疾病**：一个是"不适用/正常/野生型"，一个是"突变/患者/疾病"
3. **mRNA vs 蛋白/功能**：一个测量mRNA水平，一个测量蛋白水平/磷酸化/功能活性
4. **未刺激 vs 刺激后**：一个是未刺激/基线/对照，一个是明确刺激/感染/处理

检测到以上情况时，保留 contradicts 关系类型，但标记 `condition_mismatch=True`，后续 conflict_detector 会将其归入"不同实验条件下的结果差异"章节。

#### 双重保障机制

1. **LLM 判定层**：关系判定的 prompt 中明确列出"判定矛盾的铁律"——5种情况不能判矛盾，要求 LLM 在判定前先检查条件可比性
2. **规则后处理层**：即使 LLM 误判了，后处理规则也会自动检测明显的条件差异并标记

两层保障确保伪争议能被正确识别和分类。

### 前端综述预览（V25.6）

独立模块，不污染主程序。提供可视化的综述阅读体验，支持点击句子溯源到原文 PDF。

**访问方式**：
| 方式 | URL | 说明 |
|------|-----|------|
| 直接访问 | `http://localhost:5000/review.html` | 显示生成表单，输入主题后生成 |
| 带主题自动生成 | `http://localhost:5000/review.html?topic=STAT1&max_papers=10` | 页面加载后自动生成综述 |
| 加载已有综述 | `http://localhost:5000/review.html?review_id=rev_xxx` | 直接加载已生成的综述（1小时内有效） |

**页面布局**（左右两栏，窄屏自动切换上下布局）：
- **左侧**：综述 Markdown 渲染
  - 每个句子可点击（hover 高亮，点击后显示溯源信息）
  - 引用标记 `[ev_001]` 可直接点击，快速定位到对应证据
  - 顶部显示主题、句子数、证据数、通过率等统计
- **右侧**：PDF.js 阅读器 + 证据详情面板
  - 点击句子后，自动加载该句子关联证据对应的论文 PDF，并跳转到证据所在页码
  - 证据详情面板显示：原文引用、实验条件标签（突变类型/细胞类型/测量指标/刺激条件）、论文信息、页码
  - 支持 PDF 翻页、缩放、键盘导航

**技术实现**：
- 后端：`services/review/review_store.py`（内存暂存 + TTL 自动过期，默认 1 小时，最多 100 条）
- 前端：`frontend/review.html` + `frontend/src/review.js` + `frontend/src/review.css`（三个独立文件）
- API：`GET /api/review/<id>`（综述详情）+ `GET /api/review/<id>/sentence/<id>`（句子溯源）

---

## API 文档（V24.3）

### `GET /api/retrieve`

统一检索端点，返回证据信封。

**参数**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `q` | string | — | 检索查询（必填） |
| `top_paragraphs` | int | 6 | 返回段落数 |
| `top_figures` | int | 3 | 返回图表数 |
| `paper_id` | string | None | 限定单篇论文 |
| `section` | string | None | **V24.2** 按章节过滤（如 `Methods`、`Introduction`） |
| `year_min` | int | None | **V24.2** 最早出版年份 |
| `year_max` | int | None | **V24.2** 最晚出版年份 |
| `journal` | string | None | **V24.2** 按期刊名模糊匹配 |

**响应**：
```json
{
  "query": "...",
  "route": {"channels": ["qa", "figure", "table"], "intent": "..."},
  "paragraphs": [{"para_id": "...", "text": "...", "section_l1": "...", "page": 1, "score": 0.95}],
  "parent_contexts": [{"paper_id": "...", "section": "...", "page": 1, "text": "...►命中◄..."}],
  "chunks": [{"chunk_id": "...", "text": "...", "token_count": 750, "section_l1": "...", "para_ids": [...]}],
  "figures": [{"fig_id": "...", "fig_number": "Fig 3", "caption": "...", "file_path": "...", "page": 5}],
  "tables": [...],
  "papers": [...],
  "graph_neighbors": [{"paper_id": "...", "title": "...", "relation": "similar", "confidence": 0.72}]
}
```

### `GET /api/papers`

列出所有论文（标题、作者、期刊、年份、统计）。

### `GET /api/papers/<paper_id>`

单篇论文详情 + 图谱邻居（cites / cited_by / similar）。

### `GET /api/papers/<paper_id>/graph`

**V23.1** 从单篇论文出发的图谱遍历。参数：`relation`（cites/similar/all）、`direction`（out/in/both）、`max_hops`、`max_total`。

### `GET /api/papers/<paper_id>/pdf`

服务原始 PDF 文件（用于内置 PDF 阅读器）。

### `GET/POST /api/agentic/search`

**V23.2** Agentic 多跳检索。参数：`q`、`max_hops`（默认3，上限5）、`min_coverage`（默认0.6）、`top_paragraphs`、`paper_id`。返回含 `hops`（每跳查询/覆盖率/新增段落数）、`final_coverage`、`total_hops`、`key_entities`。

### `GET /api/communities`

**V24.3** 论文社区列表。参数：`min_size`（默认1）、`detailed=1`（含成员论文列表）。返回每个社区的代表论文、摘要、关键词、平均年份。

### `GET /api/graph/stats`

**V23.1** 图谱统计（节点数、边数、连通分量、最高被引论文）。

### `GET /api/health`

健康检查（返回当前版本号 V25.4）。

### `POST /api/review/generate`

**V25.0** 综述生成智能体。完整流水线：检索 → 证据抽取 → 大纲生成 → 撰写 → 引用校验 → Markdown 输出。核心铁律：每句话必须绑定证据卡片，无证据的句子被校验系统剔除。

**V25.9 更新**：默认生成英文综述（`language=en`），支持自定义段落级大纲（`custom_outline`），支持三种综述模板（`review_type`）。

**参数**（支持 JSON body 或 query/form，JSON body 优先级最高）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `topic` | string | — | 综述主题（必填） |
| `max_papers` | int | 20 | 最多检索的论文数 |
| `review_type` | string | narrative | 综述模板：narrative（叙事型）/ comparative（对比型）/ systematic（系统综述型） |
| `language` | string | en | 综述语言：en（英文，默认）/ zh（中文） |
| `citation_style` | string | apa | 参考文献格式：apa / nature / vancouver（需 citeproc-py） |
| `custom_outline` | object | — | V25.8 用户自定义段落级大纲（JSON，见下方格式） |
| `use_llm_verify` | bool | false | 是否启用 LLM 深度校验 |

**custom_outline 格式**（V25.8）：
```json
{
  "sections": [
    {
      "title": "章节标题",
      "description": "章节描述",
      "paragraphs": [
        {"topic": "段落主题", "description": "", "assigned_paper_ids": ["paper_001"]},
        {"topic": "另一段落主题", "assigned_paper_ids": []}
      ]
    }
  ]
}
```

**前置条件**：LLM 服务可用（本地 Ollama 或云端 OpenAI 兼容 API）。

**响应**：`{topic, markdown, references, stats, warnings, relations, conflicts, review_id}`
- `review_id`（V25.6）：综述唯一 ID，用于前端预览页加载完整数据
- `relations`（V25.3）：证据间关系列表
- `conflicts`（V25.3）：识别到的冲突点列表（含 conflict_type: true_controversy / condition_difference）

### `POST /api/review/outline`

**V25.8** 只生成段落级大纲（不撰写），返回大纲+证据卡片+论文列表，供前端展示和用户编辑。

**参数**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `topic` | string | — | 综述主题（必填） |
| `max_papers` | int | 20 | 最多检索的论文数 |
| `review_type` | string | narrative | 综述模板类型 |
| `language` | string | en | 大纲语言（V25.9） |

**响应**：`{topic, outline, evidence_cards, papers, stats, warnings}`
- `outline`：段落级大纲（章节→段落→每段主题→每段分配的论文/证据）
- `evidence_cards`：证据卡片列表
- `papers`：涉及的论文列表（paper_id + title + evidence_count）

### `POST /api/review/outline/save`

**V25.9** 保存用户编辑后的大纲到文件（`data/outlines/<name>.json`），可后续加载复用。

**请求体**（JSON）：
| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 大纲名称（必填，经 sanitize 后作为文件名） |
| `topic` | string | 综述主题 |
| `review_type` | string | 综述模板类型 |
| `outline` | object | 段落级大纲数据 |
| `paper_count` | int | 涉及论文数 |

**响应**：`{name, display_name, saved: true}`

### `GET /api/review/outline/saved`

**V25.9** 列出所有已保存的大纲（按更新时间倒序）。

**响应**：`{outlines: [{name, display_name, topic, review_type, section_count, paragraph_count, paper_count, created_at, updated_at}]}`

### `GET /api/review/outline/saved/<name>`

**V25.9** 加载指定名称的已保存大纲。

**响应**：`{name, display_name, topic, review_type, outline, paper_count, created_at, updated_at}`

**错误**：404 — 大纲不存在

### `DELETE /api/review/outline/saved/<name>`

**V25.9** 删除指定名称的已保存大纲。

**响应**：`{name, deleted: true}`

### `GET /api/review/<review_id>`

**V25.6** 获取综述完整详情（含 sentences 和 evidence_cards，用于前端预览页点击溯源）。

**路径参数**：
| 参数 | 说明 |
|------|------|
| `review_id` | 综述 ID（由 `/api/review/generate` 返回） |

**响应**：`{review_id, topic, markdown, references, stats, warnings, relations, conflicts, sentences, evidence_cards}`
- `sentences`：句子列表，每个句子含 `sentence_id`、`section_id`、`text`、`evidence_ids`、`status`
- `evidence_cards`：证据卡片字典 `{evidence_id: card}`，每张卡片含 `paper_id`、`para_id`、`page`、`content`、`original_quote`、实验条件标签等

**错误**：404 — 综述不存在或已过期（默认 TTL 1 小时）

### `GET /api/review/<review_id>/sentence/<sentence_id>`

**V25.6** 获取单个句子的溯源信息（句子详情 + 关联的证据卡片列表）。

**路径参数**：
| 参数 | 说明 |
|------|------|
| `review_id` | 综述 ID |
| `sentence_id` | 句子 ID |

**响应**：`{sentence, evidences}`
- `sentence`：句子详情（含 text、evidence_ids、status 等）
- `evidences`：关联的证据卡片列表（每张含 paper_id、page、original_quote、实验条件等）

**错误**：404 — 句子不存在

### `GET /api/review/llm_status`

**V25.0** 检查综述生成所需的 LLM 服务状态（是否可用、已安装模型列表）。

---

## 测试与自检

```bash
# 全模块测试工作流
bash scripts/run_tests.sh

# 数据库 + 检索 + 数据质量自检
python scripts/self_check.py

# 各模块独立自测
python -m services.search.chunker          # V24.1 分块器
python -m services.search.graph_traverser  # V23.1 图谱遍历
python -m services.search.agentic_search   # V23.2 Agentic
python -m build_db.build_chunks --apply    # V24.1 建块
python -m build_db.build_communities --apply  # V24.3 建社区
```

详见 `scripts/` 目录。

---

## 版本历史

| 版本 | 内容 |
|------|------|
| V20.x | 数据层：Docling + GROBID 双解析器 → SQLite + Chroma + FTS5 |
| V21.0–V21.4 | 检索层：混合检索 / RRF / Rerank / 图表向量 / 统一信封 / 查询路由 |
| V21.5 | 小→大检索（段落命中 → 整节上下文） |
| V21.6 | 重复论文去重（98→94 篇） |
| V21.7 | 参考文献条目过滤（38.6% 段落标记） |
| V21.8 | boilerplate 行级清洗（含两轮修复） |
| V22.1 | 多查询/HyDE（确定性查询变体 + 可选 LLM HyDE） |
| V22.2 | 图表→正文 DESCRIBED_IN 绑定 + 编号修正 |
| V22.3 | 论文图谱（CITES + SIMILAR + 连通度统计） |
| V22.4 | Flask API + 前端（统一检索端点 + 搜索页） |
| V23.1 | 图谱遍历（CITES/SIMILAR 边扩展 + /api/papers/<id>/graph + /api/graph/stats） |
| V23.2 | Agentic 多跳检索（hop 预算 / 实体 coverage 守卫 / 子查询 / 跨跳去重 + /api/agentic/search） |
| V23.3 | PDF.js 内置阅读器 + 双栏论文对比页面（viewer.html + compare.html） |
| V24.1 | 800token 章节感知贪心装箱分块（chunker.py + build_chunks.py + chunks 检索通道） |
| V24.2 | section/year/journal 元数据过滤（向量 Chroma $in + FTS JOIN papers 双通道） |
| V24.3 | Leiden/Louvain 社区检测 + 自动摘要（build_communities.py + /api/communities） |
| V25.0 | 综述生成智能体骨架（Pydantic模型 + Ollama接入 + 证据抽取Agent + 引用校验Agent + 撰写主流程 + /api/review/generate） |
| V25.1 | 修复 evidence_id 含空格导致引用匹配失败（sanitize + 全局短ID重映射 ev_001）+ 参考文献空paper_id过滤 |
| V25.2 | 句内定位（SentenceLocator精确到字符偏移）+ LLM大纲生成（OutlineGenerator，复用V24.3文献聚类）+ confidence_level置信度分层（风控基础字段） |
| V25.3 | 段落级关系图谱（supports/contradicts/elaborates，关键词粗筛+批量LLM判定）+ 冲突识别Agent（自动汇总矛盾点+实验条件差异分析+争议小结写入综述） |
| V25.4 | 双Provider架构（本地Ollama + 云端OpenAI兼容API，DeepSeek/阿里云等）+ Flask单线程模式（解决PyTorch模型死锁）+ SQLite线程安全 + JSON截断容错 + 云端推理速度提升10倍 |
| V25.5 | 冲突识别"伪争议"优化（区分真正矛盾 true_controversy 和实验条件差异 condition_difference，生成两个独立章节） |
| V25.6 | 前端综述预览页面（review.html 左右双栏 + PDF.js 阅读器 + 句子级溯源 + 证据详情面板 + review_id 持久化） |
| V25.7 | 综述撰写优化（三层防御：强化prompt + 后处理自动补引用 + 记录告警，pass_rate 91%→95%+）+ 参考文献CSL引擎格式化（citeproc-py + apa/nature/vancouver样式，零幻觉）+ 三种综述模板（narrative/comparative/systematic） |
| V25.8 | 段落级自定义大纲（大纲精确到每段主题 + 论文级内容分配 assigned_paper_ids + /api/review/outline 路由 + from_custom_json() + 按段落撰写 _write_paragraph()） |
| V25.9 | 大纲可视化编辑器（前端 review.html 重构：左栏大纲结构+右栏论文列表，内联编辑主题/上移下移排序/点击分配论文/保存加载大纲）+ 英文综述生成（evidence_extractor/outline_generator/review_generator 全部prompt英文化，language参数默认en，Markdown英文标题）+ 大纲文件存储（outline_store.py + 4条API路由 data/outlines/） |

### 后续 Roadmap

**V25.x — 综述生成智能体（开发中）**
- V25.0：综述 Agent 骨架（Pydantic 模型 + Ollama 接入 + 证据抽取 + 引用校验）
- V25.1：evidence_id 修复（pass_rate 41%→100%）
- V25.2：句内定位 + LLM大纲生成 + 置信度分层 ✅
- V25.3：段落级关系图谱 + 冲突识别 ✅
- V25.4：双Provider架构 + 云端API支持 ✅
- V25.5：冲突识别"伪争议"优化——分类呈现（真正矛盾 vs 条件差异型，生成两个章节）✅
- V25.6：前端综述预览页面（独立模块）—— ReviewStore综述结果暂存 + 句子级溯源API + review.html预览页（Markdown渲染 + 点击句子溯源 + PDF.js联动定位）✅
- V25.7：撰写优化（三层防御：强化Prompt + 后处理自动补引用 + 记录告警，pass_rate→95%+）✅；参考文献多格式格式化（独立citation_formatter.py模块，可扩展架构，支持GB/T 7714/APA/Nature/Vancouver四种格式，纯确定性规则，零幻觉，API通过citation_style参数切换）✅；写作标准模板（待做）

**V26+ — 远期规划**
- 句子级独立向量索引（论文量 500+ 时考虑）
- 指代消解（Contextual Retrieval，LLM 离线预处理）
- 语义切分（embedding 相似度断点）
- CLIP 图片内容向量检索
- 研究缺口自动生成
- 图表自动插入综述
- 研究脉络/观点冲突图谱可视化（Cytoscape.js）

**已决定暂缓**（详见 WORKLOG.md）：句子级独立向量库、PoC 阶段指代消解、句子级关系图谱、BGE-M3 替换、Vue3 替换、LanceDB 替换。

---

## 已知数据瑕疵

- `figures.fig_number` 原为 Docling 遇到顺序，V22.2 已从 caption 修正（445/843 修正，95 无编号，303 无 caption）
- 小→大窗口回退可能带入首页 boilerplate（V21.8 已修）
- 参考文献 DOI 解析率约 32.6%（2131/6530），CITES 边匹配受限

---

## 许可

内部项目，未开源。
