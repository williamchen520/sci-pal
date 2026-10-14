# Sci-Pal Worklog

## Current Version: V26.4

---

## 🆕 V26.4 (2026-09-26) — PMC 批量下载脚本

> **背景**：用户 Ubuntu 开发机主板烧毁，原数据库无法访问。需要一个可靠的文献批量下载方案来重建数据库。PMC (PubMed Central) 有 ~500 万篇开放获取生物医学论文，官方支持 E-utilities API + AWS S3 批量下载。

### 新增内容

1. **scripts/download_pmc.py — PMC 批量下载工具**
   - 遵循 NCBI E-utilities 官方规范（ESearch + ESummary + S3下载）
   - 支持按关键词搜索下载（自动加 open access[filter]）
   - 支持从 PMCID 列表文件批量下载
   - 支持断点续传（已下载的文件自动跳过）
   - 支持 NCBI API Key（无Key 3次/秒，有Key 10次/秒）
   - 自动获取论文元数据（标题/作者/期刊/年份/DOI/PMID），保存为 pmc_metadata.json
   - 下载失败的论文自动记录到 pmc_failed_ids.txt
   - 支持 --dry-run 预览模式（只搜索不下载）
   - 下载源：PMC OA S3 bucket (pmc-oa-opendata)，绕过 PMC 网站的 Proof-of-Work 反爬虫机制

### 技术细节

- **搜索**：ESearch API，`db=pmc`，自动加 `open access[filter]`
- **元数据**：ESummary API，批量获取（每批200篇）
- **PDF下载**：AWS S3 `pmc-oa-opendata` bucket
  - 目录结构：`PMC{id}.{version}/PMC{id}.{version}.pdf`
  - 先尝试 version .1（99%论文），失败再用 S3 prefix 搜索
  - 流式下载，自动验证文件大小（>1KB 才算有效）
- **限速**：无 API Key 0.35秒/请求，有 API Key 0.12秒/请求
- **重试**：最多3次，429限速时自动退避

### 验证结果

- ✅ 语法检查通过
- ✅ 搜索测试："STAT1 interferon" 找到 43984 篇开放获取论文
- ✅ 下载测试：PMC13614649.pdf 下载成功（2136KB，32页，PDF 1.4）
- ✅ 元数据获取正常
- ✅ 断点续传正常

### 使用示例

```bash
# 按关键词下载50篇
python scripts/download_pmc.py --query "STAT1 interferon"

# 下载200篇到指定目录
python scripts/download_pmc.py --query "JAK-STAT" --max 200 --output documents/

# 使用 API Key 提速
python scripts/download_pmc.py --query "immunology" --api-key YOUR_KEY

# 只搜索不下载
python scripts/download_pmc.py --query "cancer" --dry-run

# 从 PMCID 列表下载
python scripts/download_pmc.py --pmid-list pmc_ids.txt
```

### 文件清单
- 新增：`scripts/download_pmc.py`（~450行）
- 修改：`VERSION`（V26.3 → V26.4）
- 修改：`WORKLOG.md`（新增 V26.4 记录）

---

## 🆕 V26.3 (2026-09-25) — Windows 环境重建支持包

> **背景**：用户开发用的台式机死机/电源故障，需要在 Windows 笔记本上重建开发环境。本次更新提供完整的 Windows 重建方案，包括补全的依赖清单、一键安装脚本、一键启动脚本和详细重建指南。

### 新增内容

1. **补全 requirements.txt**
   - 原文件严重缺失（只有 Flask/openai 等6个包），实际项目用到 chromadb、sentence-transformers、PyMuPDF、docling、networkx 等
   - 分为"核心依赖"（必须）和"可选依赖"（重新建库用）两组
   - 核心依赖13个：Flask、flask-cors、Werkzeug、chromadb、sentence-transformers、PyMuPDF、requests、pydantic、networkx、tqdm、python-dotenv、pyarrow
   - 可选依赖7个：docling、docling-core、pypdf、pdfplumber、PyYAML、rich、typer
   - 附 Windows 特别说明（torch CPU版、docling编译依赖、不需要Docker/GPU）

2. **install.bat — Windows 一键安装脚本**
   - 自动检测 Python 是否安装
   - 自动创建虚拟环境 venv_sciPal
   - 自动升级 pip 并安装 requirements.txt
   - 中文提示，安装完成后给出下一步指引

3. **start.bat — Windows 一键启动脚本**
   - 内置 DeepSeek API 配置（用户只需填 API Key）
   - 自动设置 TRANSFORMERS_OFFLINE / HF_HUB_OFFLINE
   - 自动激活虚拟环境
   - 延迟2秒后自动打开浏览器 http://127.0.0.1:5000
   - 单线程启动（避免 PyTorch 死锁）

4. **README-WINDOWS.md — Windows 重建指南**
   - 系统要求（Python 3.10/3.11，不需要Docker/GPU）
   - 6步安装流程（装Python→解压→install.bat→恢复数据→配API→启动）
   - 旧电脑数据恢复清单（research.db / chroma / documents 优先级）
   - 从零开始建库的完整命令
   - 6个常见问题 FAQ
   - 目录结构说明

### 跨平台兼容性验证

- 代码路径处理全部使用 `pathlib.Path` 或 `os.path.join()`，无硬编码反斜杠
- `PROJECT_ROOT = Path(__file__).parent` 自动适配 Windows/Linux
- Flask `send_from_directory` 跨平台
- 即使硬编码了 `/` 的字符串路径，Windows API 也能接受
- 结论：代码本身无需修改，Windows 上直接运行

### 文件清单
- 新增：`requirements.txt`（完全重写，从6个包扩充到20个）
- 新增：`install.bat`（Windows一键安装）
- 新增：`start.bat`（Windows一键启动）
- 新增：`README-WINDOWS.md`（Windows重建指南）
- 修改：`VERSION`（V26.2 → V26.3）

---

## 🆕 V26.2 (2026-09-25) — Bug 修复：UnifiedRetriever 方法名错误

> **背景**：用户部署 V26.1 后测试问答功能，报错 `'UnifiedRetriever' object has no attribute 'format_envelope'`。原因是 qa_service.py 中调用了错误的方法名 `format_envelope`，而 UnifiedRetriever 中的实际方法名是 `to_envelope`。

### Bug 根因
- `services/qa/qa_service.py` 第 211 行调用 `self.retriever.format_envelope(...)`
- 但 `services/search/unified_retriever.py` 中实际方法名是 `to_envelope`（第 209 行）
- 方法签名：`def to_envelope(self, query: str, paper_id: Optional[str] = None, **kwargs) -> str`
- 该方法内部会调用 `self.retrieve(query, paper_id, **kwargs)`，然后把结果格式化为编号信封

### 修复内容
- 将 `self.retriever.format_envelope(...)` 改为 `self.retriever.to_envelope(...)`
- 注释更新为"to_envelope 内部会调用 retrieve"

### 验证方式
1. 语法检查：`python -m py_compile services/qa/qa_service.py`
2. 部署后访问 `/qa.html`，点击快捷问题"STAT1 interferon pathway"
3. 预期：不再报 `format_envelope` 错误，正常返回英文答案和引用

### 文件清单
- 修改：`services/qa/qa_service.py`（方法名 format_envelope → to_envelope）
- 修改：`VERSION`（V26.1 → V26.2）

### 📝 文档补充（2026-09-25）
- ARCHITECTURE.md 新增"三补、核心算法与外部依赖详解"章节，详细记录每个模块的算法、关键函数、第三方库
- ARCHITECTURE.md 第三方服务清单补充：Zotero（元数据导入）、NCBI（生物医学文献元数据）、Crossref API（DOI 解析）、DOI.org（DOI 重定向）
- 整理建库代码完整包（69 个文件），含 build_db/、parsers/、database/、config/、docs/

### 📌 待办功能记录（确认要做，不紧急，后面补）

**句子级切分与单向索引**
- **需求**：每个大段落下面，把句子再按句子为单位切开，每个句子标上序号，放在大段下面
- **索引设计**：单向索引——从大段能找到小句子，但句子不能反过来找大段（避免双向维护成本）
- **目的**：引用精度从段落级（[P1]）提升到句子级（[P1-S2] = 第1段第2句），答案引用更精准
- **优先级**：不紧急，核心链路（检索/问答/图谱）做完后随时补
- **当前状态**：未做。paragraphs 表只有 text 字段，无句子编号；sentence_locator.py 是综述模块运行时的句内定位，不是建库时的句子切分
- **待讨论**：句子切分规则（句号/问号/感叹号 vs NLP 工具）、存储设计（新增 sentences 表 vs paragraphs.text 嵌入编号）

---

## 🆕 V26.1 (2026-09-25) — RAG 问答英文优先：系统提示词 + 快捷问题 + 界面说明

> **背景**：用户明确指出文献库是以英文建立的（101篇全英文论文），学术问答应该优先支持英文。英文查询直接匹配英文文献，embedding 模型（all-mpnet-base-v2）是英文原生模型，FTS 对英文分词天然支持，LLM 对英文学术内容理解最深。中文作为辅助支持，不需要为了中文去换模型或加翻译模块（过度设计）。

### 变更内容
- **系统提示词改为英文**（`services/qa/qa_service.py`）：
  - 从中文"你是一个专业的学术研究助手..."改为英文"You are a professional academic research assistant..."
  - 明确规则第4条："Answer in English by default (matching the literature language for maximum accuracy)"
  - 用户提示词从"用户问题：xxx\n\n请基于上述证据回答："改为"Question: xxx\n\nAnswer based on the evidence above:"
- **无结果提示改为英文**：从"在文献库中没有找到..."改为"No relevant information was found..."
- **快捷问题改为英文**（`frontend/qa.html`）：
  - "STAT1 如何调控干扰素免疫应答？" → "How does STAT1 regulate the interferon immune response?"
  - "JAK-STAT 信号通路在癌症中的作用是什么？" → "What is the role of JAK-STAT signaling in cancer?"
  - "单细胞 RNA 测序在免疫学研究中有哪些应用？" → "What are the applications of single-cell RNA sequencing in immunology research?"
  - "质谱流式细胞术（CyTOF）的数据如何处理批次效应？" → "How to minimize batch effects in mass cytometry (CyTOF) data?"
  - 标签从"快捷问题："改为"Quick questions:"
- **新增英文优先说明**（`frontend/qa.html`）：快捷问题下方添加一行说明"📝 Answers are generated in English by default (matching literature language for maximum accuracy)"
- **界面操作保持中文**：LLM 状态、按钮、历史记录等界面文字保持中文，方便国内用户操作；只有问答内容（系统提示词、答案、快捷问题）用英文

### 设计决策
- **内容英文，界面中文**：用户是中文用户，界面操作保持中文更友好；但问答内容用英文，因为文献是英文的，英文回答更准确、更学术
- **不做自动语言切换**：不根据查询语言自动切换回答语言，统一用英文回答，避免中英文混杂导致的学术表述不严谨
- **不做查询翻译**：不需要把中文查询翻译成英文再检索，因为：
  1. 用户主要用英文提问（学术圈通用语言）
  2. 即使偶尔用中文提问，embedding 模型有一定的跨语言能力，LLM 也能理解中文问题
  3. 加翻译模块会增加延迟和复杂度，性价比不高

### 文件清单
- 修改：`services/qa/qa_service.py`（系统提示词 + 用户提示词 + 无结果提示改为英文）
- 修改：`frontend/qa.html`（快捷问题改为英文 + 新增英文优先说明）
- 修改：`VERSION`（V26.0 → V26.1）

---

## 🆕 V26.0 (2026-09-25) — RAG 学术问答模块：检索 + LLM 生成 + 引用溯源

> **背景**：检索策略优化（V25.19-V25.23）完成后，系统已经具备高质量的文献检索能力（向量+FTS+RRF+Rerank+MMR）。在此基础上新增 RAG 问答模块，让用户可以直接用自然语言提问，系统自动检索相关文献并生成带引用溯源的答案。这是"缩短阅读时间"的核心功能——用户不需要逐篇阅读，直接问直接答。

### 核心功能
- **RAG 问答服务**（`services/qa/qa_service.py`）：基于优化后的 UnifiedRetriever + LLMClient 的完整问答流水线
  - Step 1: UnifiedRetriever 检索（向量+FTS+RRF+Rerank+MMR+图谱扩展）
  - Step 2: format_envelope 构建编号信封上下文（[P1]/[F2]/[R3] 等稳定引用 ID）
  - Step 3: LLMClient 生成答案（系统提示词强制要求每个事实标注引用）
  - Step 4: 解析答案中的引用 ID，关联到具体论文和段落
  - Step 5: 返回答案 + 引用来源详情 + 检索统计 + 可选诊断信息
- **LLM 多提供商支持**：一套代码同时支持
  - **本地 Ollama**：`SCIPAL_LLM_PROVIDER=ollama`，默认模型 qwen2.5:14b
  - **DeepSeek 云端**：`SCIPAL_LLM_PROVIDER=openai`，`SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1`，`SCIPAL_LLM_MODEL=deepseek-chat`
  - **DashScope（通义千问）**：`SCIPAL_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`
  - **OpenAI 官方**：`SCIPAL_LLM_BASE_URL=https://api.openai.com/v1`
  - **任何 OpenAI 兼容服务**：自定义 base_url + api_key
- **问答 API 路由**（`api_server.py`）
  - `POST /api/qa/ask`：提问接口（参数：question, paper_id, diagnostics）
  - `GET /api/qa/status`：检查 LLM 服务状态（提供商、模型、是否可用、可用模型列表）
- **前端问答页面**（`frontend/qa.html`）
  - LLM 状态实时显示（绿色可用/红色不可用，显示提供商和模型）
  - 问题输入框（支持 Enter 发送，Shift+Enter 换行）
  - 快捷问题芯片（STAT1干扰素、JAK-STAT与癌症、单细胞测序、CyTOF批次效应）
  - 答案展示区（自动高亮引用 ID，点击可跳转到对应来源）
  - 引用来源折叠面板（按段落/图表/表格/论文分组，显示论文标题、章节、页码、原文片段）
  - 检索诊断折叠面板（JSON 格式，供调试用）
  - 问答历史记录（localStorage 存储，最多 20 条，点击可重新提问）
  - 引用来源可点击跳转到文献阅读页面（review.html?paper_id=xxx）
- **首页导航更新**：index.html 顶部新增"🤖 AI问答"入口链接

### 设计决策
- **复用现有基础设施**：不重复造轮子，直接使用已优化的 UnifiedRetriever（V25.23）和已有的 LLMClient（V25.4）
- **编号信封引用机制**：沿用 V21.3 建立的统一信封格式，LLM 输出 [P1]/[F2] 等稳定 ID，前端解析后关联到具体来源
- **防幻觉系统提示词**：明确要求"只使用证据中包含的信息，不要编造或引入外部知识"、"每个事实性陈述都必须标注引用来源"、"如果证据不足以回答问题，请明确说明"
- **懒加载**：QAService 采用懒加载单例模式，首次请求时才初始化检索器和 LLM 客户端，保持启动速度
- **单轮问答**：第一版先做单轮问答（不保留对话上下文），降低复杂度；多轮对话可后续迭代

### 文件清单
- 新增：`services/qa/__init__.py`
- 新增：`services/qa/qa_service.py`（约 350 行）
- 新增：`frontend/qa.html`（约 450 行，含 CSS+JS）
- 修改：`api_server.py`（新增 _qa_service 懒加载变量、get_qa_service() 函数、/api/qa/ask 和 /api/qa/status 路由）
- 修改：`frontend/index.html`（顶部导航新增 AI 问答入口，页脚版本号更新）
- 修改：`VERSION`（V25.23 → V26.0）

### 部署配置示例
```bash
# 方式1：本地 Ollama（推荐，数据不出本地）
export SCIPAL_LLM_PROVIDER=ollama
export SCIPAL_LLM_MODEL=qwen2.5:14b
# 先启动 Ollama 并拉取模型：ollama serve && ollama pull qwen2.5:14b

# 方式2：DeepSeek 云端（速度快，质量高）
export SCIPAL_LLM_PROVIDER=openai
export SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
export SCIPAL_LLM_API_KEY=sk-你的DeepSeek_Key
export SCIPAL_LLM_MODEL=deepseek-chat

# 启动服务
python api_server.py
# 打开 http://localhost:5000/qa.html
```

### 验证方式
1. 语法检查：`python -m py_compile services/qa/qa_service.py api_server.py`
2. 启动服务后访问 `http://localhost:5000/api/qa/status`，确认 LLM 状态返回正确
3. 访问 `http://localhost:5000/qa.html`，输入问题测试问答功能
4. 检查答案中是否包含引用 ID（如 [P1]），点击引用是否跳转到对应来源
5. 检查引用来源面板是否正确显示论文标题、章节、页码、原文片段

---

## 🆕 V25.23 (2026-09-25) — MMR 默认参数调优：λ=0.6

> **背景**：V25.22 修复 MMR 流程后，调优脚本在真实数据库上跑出了有意义的结果。根据调优结果，将默认 MMR_LAMBDA 从 0.7 调整为 0.6。

### 调优结果（真实数据库，8 个标准查询，top_k=10）

| λ 值 | 平均论文数 | 最大论文占比 | 平均相关分 | 评价 |
|------|----------|------------|----------|------|
| 0.5 | 4.25 | 61.3% | 0.6098 | 偏多样性 |
| **0.6** | **4.25** | **61.3%** | **0.6196** | **平衡（推荐）** |
| 0.7 | 3.88 | 65.0% | 0.6296 | 平衡 |
| 0.8 | 3.75 | 66.2% | 0.6318 | 偏相关性 |
| 0.9 | 3.62 | 67.5% | 0.6331 | 偏相关性 |
| 1.0 | 3.38 | 67.5% | 0.6359 | 纯相关性（无MMR） |

### 为什么选 λ=0.6？
- **多样性最优**：和 λ=0.5 一样，平均涉及 4.25 篇论文，最大占比 61.3%
- **相关性更好**：平均相关分 0.6196，比 λ=0.5 的 0.6098 高 1.6%
- **性价比最高**：在多样性不损失的前提下，相关性更高

### 对比修复前（V25.20 及之前）
- 修复前：所有 λ 值结果完全相同（平均论文数 3.0，最大占比 70%）
- 修复后：λ=0.6 比 λ=1.0 多涉及 0.87 篇论文（+26%），最大占比降低 6.2 个百分点
- MMR 多样性去重真正生效了

### 修改文件
- `services/search/hybrid_search.py` — `MMR_LAMBDA` 从 0.7 改为 0.6

### 部署注意事项
1. 只改了一个常量，覆盖 `services/search/hybrid_search.py` 即可
2. 无需重建数据库/向量索引/FTS
3. 如果后续觉得多样性不够或相关性下降，可自行调整 `MMR_LAMBDA`（参考调优结果表格）

---

## 🆕 V25.22 (2026-09-25) — MMR 修复第二弹：rerank 候选池扩大，MMR 真正生效

> **背景**：V25.21 修复了 MMR 内部参数（阈值+停用词+跨论文奖励），但部署后调优脚本结果仍然所有 λ 值相同。进一步排查发现是**流程问题**：MMR 在 rerank 截断之后才执行，候选池只有 10 段，MMR 无法引入更多论文。

### 问题现象
- V25.21 部署后，调优脚本所有 λ 值（0.5-1.0）结果仍然完全相同
- 平均涉及论文数：3.0（所有 λ 值相同）
- 最大论文占比：70.0%（所有 λ 值相同）

### 根因分析（流程级 bug）
```
当前流程（错误）：
  混合检索 → rerank(截断到 top_k=10段) → MMR(在这10段里重新排序)

问题：rerank 已经把候选截断到 10 段了，而这 10 段里本身就只有 3 篇论文。
MMR 只能在这 10 段里重新排序，无法引入第 4 篇论文。
所以无论 λ 怎么调，涉及的论文数都是 3，MMR 形同虚设。
```

### 修复方案
```
修复后流程（正确）：
  混合检索 → rerank(保留 top_k×3=30段，不截断) → MMR(从30段里多样性选10段)
```

具体修改：
1. **`unified_retriever.py`**：rerank 时传入 `rerank_k = min(top_paragraphs * 3, len(fused))`，保留 3 倍候选；MMR 条件从 `> top_paragraphs // 2` 改为 `> top_paragraphs`
2. **`hybrid_search.py`**：同样的修改，rerank 保留 3 倍候选，MMR 条件改为 `> top_k`

### 为什么是 3 倍？
- 1 倍（10段）：候选池太小，MMR 无法引入新论文
- 2 倍（20段）：可能够用，但 rerank 本身有计算成本，2 倍性价比一般
- 3 倍（30段）：足够 MMR 从更多论文中选择，rerank 成本增加可控（cross-encoder 推理 30 段 vs 10 段，约增加 2 倍时间，但检索整体延迟仍在可接受范围）
- 后续可根据实际延迟和效果调整这个倍数

### 修改文件
- `services/search/unified_retriever.py` — rerank 候选池扩大到 3 倍
- `services/search/hybrid_search.py` — rerank 候选池扩大到 3 倍

### 部署注意事项
1. 纯流程修复，无需重建数据库/向量索引/FTS
2. 覆盖 `services/search/unified_retriever.py` 和 `services/search/hybrid_search.py`
3. 部署后重新运行调优脚本，应该能看到不同 λ 值产生不同结果
4. 注意：rerank 延迟会增加约 2 倍（从 10 段增加到 30 段），如果延迟不可接受，可将 3 倍改为 2 倍

---

## 🆕 V25.21 (2026-09-25) — MMR 多样性去重修复：真正生效

> **背景**：V25.20 部署后运行调优脚本，发现所有 MMR_LAMBDA 值（0.5-1.0）的检索结果完全相同（平均论文数=3.0，最大占比=70%），说明 MMR 多样性去重实际上没有生效。

### 问题现象
- 调优脚本 `tune_retrieval.py` 测试 λ=0.5 到 λ=1.0，所有指标完全一致
- 平均涉及论文数：3.0（所有 λ 值相同）
- 最大论文占比：70.0%（所有 λ 值相同）
- 平均相关分：0.6376（所有 λ 值相同）

### 根因分析（因果链）
1. **直接原因**：MMRDiversifier 中 `MIN_SIMILARITY = 0.15` 阈值过高
2. **中间机制**：学术论文段落之间用词差异大，全部词的 Jaccard 相似度普遍低于 0.15
3. **结果**：相似度低于阈值的段落对不互相惩罚 → 多样性惩罚始终为 0 → MMR 退化成纯相关性排序 → λ 怎么调都没用
4. **加剧因素**：`_tokenize()` 不过滤停用词，"the/and/of/in" 等无区分度的词大量出现，进一步稀释了 Jaccard 相似度
5. **次要因素**：跨论文多样性奖励 `paper_penalty=0.05` 太小，不足以推动选择不同论文

### 修复方案（3 处修改）
1. **降低相似度阈值**：`min_similarity` 从 0.15 降到 0.03，让更多段落对能触发多样性惩罚
2. **过滤停用词**：`_tokenize()` 新增 150+ 停用词过滤（含学术常见词如 fig/table/et/al/cf/e.g 等），提升 Jaccard 相似度的敏感度
3. **增加跨论文奖励**：`paper_penalty` 从 0.05 提升到 0.1，更鼓励选择不同论文的段落

### 修复效果验证
用模拟数据测试（前 3 条来自同一篇论文且内容相似，后 3 条来自不同论文）：
| λ 值 | 排序（论文ID） | 涉及论文数 |
|------|--------------|----------|
| 1.0（纯相关性） | A, A, A, B | 2 |
| 0.7（平衡） | A, A, B, A | 2 |
| 0.5（偏多样性） | A, B, A, C | 3 |

✅ 不同 λ 值现在产生不同结果，MMR 真正生效。

### 修改文件
- `services/search/mmr_diversifier.py` — 3 处修复（阈值+停用词+跨论文奖励）

### 部署注意事项
1. 纯算法层修复，无需重建数据库/向量索引/FTS
2. 覆盖 `services/search/mmr_diversifier.py` 即可
3. 部署后重新运行调优脚本，应该能看到不同 λ 值产生不同结果
4. 建议用调优脚本在真实数据库上重新测试，选择最优 λ 值

---

## 🆕 V25.20 (2026-09-25) — V25.19补充优化：大纲存储修复 + 调参脚本 + 学术缩写扩展词典

> **背景**：V25.19 检索策略优化部署后，根据自检结果和用户反馈做的补充优化和 bug 修复。

### 修复1：V25.9 大纲存储自测失败
- **问题**：自检报告中大纲存储 2 项失败：列表 0 个大纲、`'str' object has no attribute 'get'`
- **根因**：`scripts/self_check.py` 调用 `store.save()` 时参数顺序传错——把字符串 `"narrative"` 传给了 `outline_data` 参数（应为 dict），把 dict `test_outline` 传给了 `review_type` 参数（应为 str）。导致 `record["outline"]` 变成字符串，后续 `list()` 中调用 `.get("sections")` 时报错
- **修复**：改用关键字参数调用，避免位置参数顺序错误
- **修改文件**：`scripts/self_check.py`

### 新增1：检索参数调优脚本
- **功能**：在真实数据库上自动测试不同 `MMR_LAMBDA` 值的效果，输出对比表格和参数推荐
- **测试指标**：平均涉及论文数（多样性）、最大论文占比（冗余度）、平均相关分（相关性）
- **标准查询**：8 个覆盖不同类型（实体密集型、自然语言型、技术短语型）
- **使用方法**：`TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python3 scripts/tune_retrieval.py`
- **新增文件**：`scripts/tune_retrieval.py`

### 新增2：学术缩写扩展词典
- **问题**：用户常用缩写查询（如 "STAT1 KO mice"、"PD-1 blockade"），但论文中可能用全称（knockout、programmed death 1），导致 FTS 漏匹配
- **解决方案**：
  - 收录 **150+ 生物医学常见缩写**（基因操作 KO/KD/OE、免疫检查点 PD-1/CTLA-4、细胞因子 IFN/IL/TNF、技术方法 FACS/ELISA/scRNA-seq、疾病 GvHD/IBD 等）
  - 缩写自动扩展为全称，生成更多查询变体，通过 RRF 融合提升召回率
  - 高置信度优先，只收录无歧义或低歧义的常见缩写
  - 纯确定性词典，零成本，无需 LLM
- **效果示例**：
  - `STAT1 KO mice` → `STAT1 knockout mice`
  - `PD-1 blockade` → `programmed cell death protein 1 blockade`
  - `scRNA-seq analysis of TME` → `scRNA-seq analysis of tumor microenvironment`
- **新增文件**：`services/search/abbreviation_expander.py`
- **修改文件**：`services/search/query_expander.py` — 集成缩写扩展

### 修复2：query_expander 实体识别正则 bug
- **问题**：`STAT1` 这种"全大写+数字"的基因符号未被识别（原正则 `[A-Z][a-z]*\d+` 只匹配首字母大写后续小写，如 Stat1）
- **修复**：正则改为 `[A-Z][A-Za-z]*\d+(?:[a-z])?`，允许后续字母大写或小写
- **修改文件**：`services/search/query_expander.py`

### 自检脚本更新
- 新增 V25.20 检查项：缩写扩展模块识别、扩展生成变体、query_expander 集成验证
- 修复大纲存储自测的参数顺序错误
- **修改文件**：`scripts/self_check.py`

### 部署注意事项
1. 纯算法层优化 + bug 修复，无需重建数据库/向量索引/FTS
2. 4 个新文件放到 `services/search/` 和 `scripts/` 目录
3. 4 个修改文件覆盖同名文件
4. 部署后运行自检，预期大纲存储 2 项失败消失，V25.20 新增检查全部通过

---

## 🆕 V25.19 (2026-09-25) — 检索策略优化：增强FTS查询 + 动态RRF权重 + MMR多样性去重 + 检索诊断模式

> **背景**：数据治理完成后（去重192→101篇、向量索引全量重建17397条、FTS重建、知识图谱重建），进入检索精度优化阶段。V21-V24已建立完整检索架构（混合检索+多查询扩展+重排序+查询路由+上下文扩展+图谱遍历），V25.19在此基础上做4项高性价比优化。

### 优化1：增强 FTS 查询构建器（`services/search/fts_query_builder.py`）
- **问题**：原 FTS 查询用简单 `OR` 连接所有词，丢失了短语结构和实体权重
- **解决方案**：
  - **实体识别**：自动识别基因/蛋白符号（STAT1、p53）、缩写（JAK、MHC-II）、干扰素/白介素（IFN-γ、IL-6）、连字符技术词（JAK-STAT、PI3K-AKT）
  - **短语匹配**：多词实体和技术化合物用引号包裹，作为短语匹配而非独立词
  - **NEAR 操作符**：关键词对用 `NEAR(term1 term2, 10)` 限制词间距，提升共现段落权重
  - **实体加权**：实体词权重 ^3，短语权重 ^2，普通关键词权重 ^1
  - **优雅回退**：增强查询语法出错时自动回退到简单 OR 查询，永不返回空
- **新增文件**：`services/search/fts_query_builder.py`
- **核心类**：`FTSQueryBuilder` — `build(query)` / `build_simple(query)` / `explain(query)`

### 优化2：动态 RRF 权重（`hybrid_search.py`）
- **问题**：原 RRF 融合中向量和 FTS 权重固定 1:1，但不同查询类型最优权重不同
- **解决方案**：
  - **实体密集型查询**（如 "STAT1 JAK-STAT phosphorylation"）：FTS 权重提升（精确匹配更重要）
  - **自然语言型查询**（如 "How does the immune system respond to viral infection?"）：向量权重提升（语义匹配更重要）
  - **计算方式**：统计查询中的实体数量，每实体 +0.5 FTS 权重（上限 +1.0）；长查询且实体密度低时 +0.3 向量权重
- **修改文件**：`services/search/hybrid_search.py`
- **新增方法**：`_compute_dynamic_weights(query)` → `(vector_weight, fts_weight)`
- **修改方法**：`rrf_fuse()` 新增 `vector_weight` / `fts_weight` 参数

### 优化3：MMR 多样性去重（`services/search/mmr_diversifier.py`）
- **问题**：重排序后常返回同一篇论文/同一章节的多个相似段落，LLM 上下文冗余浪费
- **解决方案**：
  - **MMR 公式**：`MMR(D_i) = λ * Relevance(D_i) - (1-λ) * max_{D_j in S} Similarity(D_i, D_j)`
  - **λ=0.7**：偏相关性但适度多样化（推荐默认值）
  - **相似度计算**：基于词集合的 Jaccard 相似度（轻量，无需模型）
  - **跨论文多样性奖励**：选择不同 paper_id 的候选时 +0.05 奖励，鼓励跨论文覆盖
  - **最小相似度阈值**：相似度 <0.15 的候选不互相惩罚，避免过度惩罚不相关项
- **新增文件**：`services/search/mmr_diversifier.py`
- **核心类**：`MMRDiversifier` — `diversify()` / `diversify_with_diagnostics()`

### 优化4：检索诊断模式（`services/search/retrieval_diagnostics.py`）
- **问题**：检索是黑盒，不知道为什么返回这些结果、每一步发生了什么
- **解决方案**：
  - **全链路捕获**：查询路由 → 查询扩展 → FTS查询构建 → 向量检索原始结果 → FTS检索原始结果 → RRF融合详情 → 重排序前后对比 → MMR去重前后对比 → 最终结果
  - **RRF 融合详情**：哪些条目同时出现在向量和FTS中、各自排名、融合分数
  - **重排序对比**：候选数量、位置变化数、Top5 前后对比、分数范围
  - **MMR 诊断**：多样性提升值、唯一论文数变化、重排数量
  - **文本报告**：`format_text_report()` 生成人类可读的诊断报告
  - **零开销**：默认关闭，`diagnostics=True` 时才启用
- **新增文件**：`services/search/retrieval_diagnostics.py`
- **核心类**：`RetrievalDiagnostics` — `start()` / `log()` / `set_result()` / `finish()` / `format_text_report()`

### 优化5（补充）：学术缩写扩展词典（`services/search/abbreviation_expander.py`）
- **问题**：用户常用缩写查询（如 "STAT1 KO mice"、"PD-1 blockade"），但论文中可能用全称（knockout、programmed death 1），导致 FTS 漏匹配
- **解决方案**：
  - **生物医学缩写词典**：收录 150+ 常见缩写（基因操作 KO/KD/OE、免疫检查点 PD-1/CTLA-4、细胞因子 IFN/IL/TNF、技术方法 FACS/ELISA/scRNA-seq、疾病 GvHD/IBD 等）
  - **双向扩展**：缩写→全称，生成更多查询变体
  - **高置信度优先**：只收录无歧义或低歧义的常见缩写，避免误扩展
  - **集成到 query_expander**：查询扩展时自动包含缩写扩展变体，通过 RRF 融合提升召回率
  - **零成本**：纯确定性词典查找，无需 LLM
- **新增文件**：`services/search/abbreviation_expander.py`
- **核心类**：`AbbreviationExpander` — `expand_abbreviations()` / `get_expansion_variants()` / `get_abbreviation_info()`
- **修改文件**：`services/search/query_expander.py` — 集成缩写扩展，修复实体识别正则（STAT1全大写+数字）

### 集成修改
- **`services/search/hybrid_search.py`**：
  - 新增配置常量：`ENHANCED_FTS`、`DYNAMIC_RRF_WEIGHTS`、`MMR_DIVERSIFY`、`MMR_LAMBDA`
  - `__init__` 初始化 `FTSQueryBuilder`、`MMRDiversifier`、`RetrievalDiagnostics`
  - `fts_search()` 使用增强查询构建器，异常时回退简单查询
  - `search()` 集成 MMR 去重（rerank 后执行）和诊断模式
  - `_retrieve_candidates()` 使用动态权重
- **`services/search/unified_retriever.py`**：
  - `__init__` 新增 `diagnostics` 参数，传递给 HybridSearch
  - `retrieve()` 记录路由诊断，结果中包含 `diagnostics` 字段
  - 新增 `get_diagnostics_report()` 方法

### 自检脚本更新（`scripts/self_check.py`）
- 新增 `check_v25_19_retrieval_optimization()` 检查函数，覆盖：
  - FTS 查询增强模块：实体识别、短语检测、查询构建、简单回退
  - MMR 去重模块：运行成功、mmr_rank 字段、诊断模式
  - 检索诊断模块：运行、总耗时、文本报告
  - hybrid_search.py 配置项和导入检查
  - unified_retriever.py 诊断参数检查
- 约 20 项新检查

### 配置开关（可在 `hybrid_search.py` 顶部调整）
```python
ENHANCED_FTS = True            # 增强 FTS 查询
DYNAMIC_RRF_WEIGHTS = True    # 动态 RRF 权重
MMR_DIVERSIFY = True           # MMR 多样性去重
MMR_LAMBDA = 0.7               # MMR 相关性-多样性平衡（1.0=纯相关性）
```

### 部署注意事项
1. 纯算法层优化，无需重建数据库/向量索引/FTS
2. 无需新模型、无需训练、不增加外部依赖
3. 所有优化默认开启，可通过配置常量关闭
4. 诊断模式默认关闭，需要时 `UnifiedRetriever(diagnostics=True)` 或 `HybridSearch(diagnostics=True)`

---

## 🆕 V25.18 (2026-09-24) — 引用编号优化 + paper表字段补充 + PDF端口深化

### 任务1：引用编号优化
- **问题**：正文中用 `[ev_xxx]` 证据 ID 作为引用标记，读者看不懂，和末尾参考文献列表没有对应关系
- **解决方案**：
  - 建立 `evidence_id → paper_id → 参考文献编号` 映射，编号按正文首次出现顺序分配
  - 正文渲染时把 `[ev_xxx]` 替换成 `[n]`，同一篇论文的多个证据引用同一个编号
  - 多引用合并：连续编号合并成 `[1-3]`，非连续用 `[1,3,5]`
  - 参考文献列表按正文出现顺序排列，带编号前缀（`1. xxx`、`2. xxx`）
  - 研究争议章节中的引用标记也同步转换
- **修改文件**：`services/review/review_generator.py`
- **新增方法**：`_format_ref_numbers()` — 格式化参考文献编号，支持连续编号合并

### 任务2：补充 paper 表字段
- **新增字段**（9个）：
  - `abstract TEXT` — 摘要（之前缺失！）
  - `paper_type TEXT DEFAULT 'J'` — 文献类型（J/C/M/D）
  - `publisher TEXT` — 出版商
  - `language TEXT DEFAULT 'en'` — 语言
  - `affiliations TEXT` — 作者单位
  - `funding TEXT` — 基金资助
  - `parse_status TEXT DEFAULT 'completed'` — 解析状态
  - `parse_engine TEXT` — 解析引擎
  - `updated_at TEXT DEFAULT CURRENT_TIMESTAMP` — 更新时间
- **修改文件**：
  - `build_db/build_database.py` — 表结构
  - `build_db/db_writer.py` — 插入逻辑
- **新增文件**：`migrate_papers_table_v25.18.py` — 数据库迁移脚本（给已有数据库添加新字段）
- **迁移方法**：`python3 migrate_papers_table_v25.18.py [数据库路径]`

### 任务3：PDF 端口设计深化
- **新增功能**：从解析结果中自动提取 abstract、affiliations、funding 字段
- **实现方式**：
  - 扫描段落的章节标题，匹配 abstract/affiliations/funding 的多种命名模式
  - 收集后续正文段落内容直到下一个章节标题
  - Nature 的首段加粗摘要（已识别为 section_type=abstract）自动提取为 abstract
  - 对所有期刊（包括未识别家族的）都执行通用提取
- **修改文件**：`build_db/parsers/journal_optimizer.py`
- **新增函数**：`extract_metadata_fields()` — 提取 abstract/affiliations/funding

### 任务4：Zotero 元数据导入脚本
- **新增文件**：`import_zotero_metadata.py`
- **用途**：从 Zotero 导出的 CSL JSON 文件中提取元数据，批量补全/更新 Sci-Pal papers 表
- **工作原理**：不直接读 Zotero 数据库（zotero.sqlite），而是读 Zotero 导出的 CSL JSON 标准格式文件
- **使用流程**：
  1. Zotero 中选中文献 → 右键导出 → 格式选 "CSL JSON" → 保存为 .json
  2. 运行：`python3 import_zotero_metadata.py zotero_export.json data/research.db`
- **匹配策略**：
  1. DOI 精确匹配（归一化后，最准确）
  2. 标题模糊匹配（归一化后去标点转小写，兜底）
  3. 都匹配不上 → 跳过并记录
- **更新字段**：title、authors、journal、doi、year、volume、issue、pages、abstract、publisher、language、paper_type、keywords、parse_engine（标记为 zotero_import）
- **CSL 字段映射**：`container-title`→journal，`issued.date-parts[0][0]`→year，`author[]`（family+given）→分号分隔字符串，`type`→paper_type（article-journal→J, book→B, chapter→C, thesis→T, report→R）
- **关键函数**：`normalize_title()`、`normalize_doi()`、`format_authors()`、`extract_year()`、`clean_text()`、`import_zotero_metadata()`
- **输出统计**：DOI匹配数、标题匹配数、未匹配数、各字段更新计数、abstract填充数、未匹配文献列表、更新后abstract填充率验证

### 部署注意事项
1. 运行数据库迁移脚本：`python3 migrate_papers_table_v25.18.py data/research.db`
2. 重新解析论文时，新字段会自动填充
3. 已有的94篇论文需要重新解析才能填充 abstract 等新字段（或手动补充）

---

## 📋 Active Issues

### Issue #1: GROBID Docker unavailable from China
- **Date**: 2026-09-18
- **Status**: ⏸️ Deferred
- **Problem**: Cannot pull `lfoppiano/grobid:0.8.0` from Docker Hub - timeout/blocked from China
- **Current workaround**: Skip GROBID, citations return empty
- **Future solutions to explore**:
  - [ ] Chinese Docker mirror setup (USTC, NetEase, Baidu)
  - [ ] Pure Python citation parser alternative
  - [ ] Self-hosted GROBID build from source
  - [ ] Use Crossref API instead of local GROBID
- **Priority**: Medium (not blocking core functionality)

---

## 📝 Completed Work

### V0.1 - V0.7 Scaffolding (2026-09-18)
- [x] Project skeleton setup
- [x] Database schema design (papers, paragraphs, figures, citations)
- [x] Offline build_db / online service separation
- [x] Parser orchestrator architecture
- [x] Query API layer (text, figure, citation, paper search)
- [x] AI Q&A with strong RAG (envelope + validation + retry)
- [x] Real LLM connection (OpenAI-compatible API)
- [x] Basic frontend UI (search, chat, upload tabs)
- [x] Test data seeder
- [x] Real parser integrations (MinerU, pdfplumber, GROBID stub)

---

## 🚀 Future Improvements

### Priority 1 (Next)
- [ ] Improve frontend: paper details view
- [ ] Streaming AI response
- [ ] Fix GROBID citation parsing

### Priority 2
- [ ] Performance optimizations (caching, indexes)
- [ ] PDF viewer in browser
- [ ] Better chat UI with markdown rendering

### Priority 3 (L3 Features)
- [ ] Knowledge graph visualization
- [ ] Literature review generation
- [ ] Entity extraction from papers
- [ ] Multi-paper comparison

---

## 📌 Architecture Decisions

### 1. Offline / Online Separation
- build_db/ directory is completely separate from main service
- Heavy parsing dependencies (MinerU, GROBID, etc.) are only in build_db/
- Main server only has lightweight query code
- **Why**: Keep the online service fast and lean; avoid heavy dependencies in production

### 2. Single Physical DB, Logical Multi-Table
- Physical: ONE SQLite file (research.db)
- Logical: Multiple tables separated by domain:
  - Text domain: papers, paragraphs, chunks
  - Figure domain: figures, tables
  - Citation domain: citations
  - User domain: (future)
- **Why**: Simple deployment, but clean logical separation

### 3. ⚠️ CRITICAL: Data Layer Architecture V2 (Major Simplification)
**Date: 2026-09-18**

**Decision: We drastically simplified the data layer!**

From "multi-parser + coordinate alignment" → "single parser + universal index"

| Old Design (Complex) | New Design (Simple) |
|---------------------|---------------------|
| Multi-parser (MinerU + GROBID + pdfplumber) | Single parser (Docling) |
| Pixel-level coordinate alignment | ID-based matching |
| 800 manual rules | Zero rules, fully automatic |
| Cross-validation between parsers | No cross-validation |
| N association tables | One universal index table |

**What we kept:**
- ID-based matching
- Forward/reverse indexes
- Hierarchical structure
- Offline/online separation
- Strong RAG pattern

**Why we changed:**
- We were overengineering!
- Multi-parser coordination is too complex
- Coordinate alignment is overkill for our use case
- Single parser + universal index is much simpler and faster to build
- **Philosophy: Run one paper first, then batch. Don't overthink it!**

**Design docs:**
- `docs/DATA_LAYER_ARCHITECTURE_V2.md` - detailed design
- `docs/DATA_LAYER_ARCHITECTURE_V2.html` - visual diagram

### 4. Strong RAG Pattern
- Same as etymology project: numbered envelope + coverage validation + automatic retry
- AI must cite specific reference IDs
- If coverage < 90%, automatically retry with specific guidance
- **Why**: Prevent AI hallucination; ensure all claims are grounded in our data

### 5. Parser Strategy (V2: Single Parser)
- **Primary**: Docling (single parser, does everything)
- **Old approach (abandoned)**: MinerU + GROBID + pdfplumber multi-parser
- **Why single parser?**: 
  - Much simpler to implement
  - No need to align coordinates between parsers
  - One output format, no integration headache
  - If Docling isn't good enough, we can swap later
- **Philosophy**: Start simple, iterate later. Don't overengineer!

### 6. How Tables "Communicate" (Paper ID as the Glue)
**Important: Tables do NOT talk to each other directly!**

The "communication" between different tables (text, figures, citations) happens through:

#### Shared `paper_id` (the only connection!)
- Every table has a `paper_id` column
- All records from the same PDF share the same `paper_id`
- No foreign keys, no joins at the database level
- No direct communication between tables

#### How it works:
1. **Build time**: Each parser gets the same `paper_id` and writes to its own table
   ```
   Paper ID: paper_mmc4_xxx
   ├── paragraphs table: 50 rows with paper_id = paper_mmc4_xxx
   ├── figures table: 5 rows with paper_id = paper_mmc4_xxx
   └── citations table: 30 rows with paper_id = paper_mmc4_xxx
   ```

2. **Query time**: The retrieval layer queries each table separately, then combines results in code
   ```
   Step 1: Query paragraphs WHERE paper_id = ?
   Step 2: Query figures WHERE paper_id = ?
   Step 3: Query citations WHERE paper_id = ?
   Step 4: Combine all results in Python code into one envelope
   ```

#### Why we do it this way:
- ✅ **Simple**: No complex joins, no foreign key constraints
- ✅ **Independent**: Each table can be modified/rebuilt without affecting others
- ✅ **Fallback friendly**: If one table is empty (e.g., no GROBID), the rest still works
- ✅ **Debuggable**: Easy to trace which parser produced what
- ❌ **What we DON'T do**:
  - No SQL JOINs across tables
  - No database-level relationships
  - No triggers or stored procedures
  - Tables are completely self-contained

**This is the same philosophy as "physical separation, logical integration" - the database stays simple, all the intelligence is in the retrieval layer.**

---

## 📅 2026-09-21 工作日志

### V20.4 — GROBID 正文引用链接
- 发现 GROBID TEI XML 自带 `<ref type="bibr" target="#b6">` 引用链接
- 扩展 `grobid_parser.py`，新增 `parse_intext_citations()`
- 批量测试 64 篇：4,948 条参考文献 → 8,004 条正文引用链接（平均 125/篇）
- 比正则匹配（5,989 条）多 33%，且更准确（直接锚定）
- 已接入 `build_database.py`，存入 paper_index，关系类型 `grobid_cites`

### 查尔姆斯理工论文调研
- 论文：《Towards Reliable Retrieval Systems: Design and Evaluation of an Agentic GraphRAG Pipeline》
- 作者：Adam Spreitz，Chalmers University of Technology，2026
- 确认我们架构方向正确：GROBID 头尾 + Docling 中间 + VLM 兜底
- 他们技术栈：Neo4j（图库+向量库）+ all-mpnet-base-v2 + BM25 + RRF
- 没有公开源代码

### V21.0 — 检索层搭建
- `build_embeddings.py`：给 17,336 段文字生成向量嵌入，存入 Chroma
  - 模型：all-mpnet-base-v2（768 维）
  - 国内镜像：HF_ENDPOINT=https://hf-mirror.com
- `build_fts.py`：SQLite FTS5 全文索引
- `hybrid_search.py`：混合检索（向量 + 全文 + RRF 融合排序）
- 修了 3 个 bug：PROJECT_ROOT 路径层级、FTS 表别名破坏 MATCH、标点 `?` 粘词导致 FTS5 静默报错（改为正则提词 + 英文停用词过滤）

### V21.1 — Cross-Encoder 重排序
- `reranker.py`：BAAI/bge-reranker-base（CrossEncoder，约 1.11GB）
- 两阶段：混合召回 20 → cross-encoder 精排到 5
- 验证：把"关键词列表"段从 RRF 第 1 名降下去，真正解释段提到第 1（0.999）
- 已集成进 HybridSearch.search(rerank=True)

### V21.2 / V21.2.1 — 图表向量索引
- 图按图注文本 embedding；表按"表注 + markdown 内容"（截断 1500 字）embedding
- 修了幂等 bug（原来段落已存在就提前 return，跳过图表；现每个集合各自检查计数）
- 已建数量：**图 582、表 182、论文 98、段落 16,802**
- 图/表语义检索实测准确（搜 TNNT1 肝纤维化 → 正确命中 Fig 10/13/12）

### V21.3 — 统一证据信封
- `unified_retriever.py`：一个查询扇出到 段落[Pn] / 图[Fn] / 表[Tn] / 论文[Rn]
- `retrieve()` 返回结构化 dict；`to_envelope()` 生成带编号的文本信封，强制 LLM 引用 [P1]/[F2]
- 传 paper_id 时限定单篇、自动跳过跨论文搜索
- 接上 strong RAG 设计：编号信封 + 覆盖率校验 + 自动重试

### V21.4 — 查询路由
- `query_router.py`：规则（正则+关键词，中英文）分类通道 qa/figure/table/citation/papers
- QA 段落通道永远跑（兜底）；单篇内自动跳过跨论文；只跑需要的通道，省算力降噪音
- 已接进 UnifiedRetriever(routing=True)
- 规则零成本、毫秒级、可调试；以后规则分不准再加 LLM 分类器兜底

### 当前数据规模
- 论文：111 篇（成功 104，失败 7）
- 段落：17,336 段（全部带坐标；FTS 索引 16,800；向量 16,802）
- 图片：894 行（582 带图注已 embedding）
- 表格：201 个（182 已 embedding）
- 参考文献：6,775 条（83.4% 带 DOI）
- 正文引用链接：GROBID 8,004 条（旧正则 5,989 条保留作对比，不删）
- 跨论文引用：22 条

---

## 🔬 Chalmers 论文深度调研（内部关系 + 网络构建）

**论文**：《Towards Reliable Retrieval Systems: ...Agentic GraphRAG Pipeline》Adam Spreitz, Chalmers, 2026（无公开源代码）

### 他们的图关系全集（论文表 4.1，共 12 种边）
| 关系 | 方向 | 我们的状态 |
|---|---|---|
| HAS_SECTION / HAS_CHUNK | 论文→章节→段落 | 有（section_level / sequence 字段） |
| NEXT_SECTION / NEXT_CHUNK | i→i+1 阅读顺序 | 有（sequence） |
| HAS_FIGURE / HAS_TABLE / HAS_EQUATION | **章节→图/表/公式** | 部分（现挂论文，未挂章节；公式无） |
| **DESCRIBED_IN** | **图/表→段落**（视觉元素连到引用它的正文） | ⚠️ 待做（正是下一步图表绑定） |
| CITES | **论文→论文/文献**（仅论文级） | 有，且我们更细 |
| HAS_AUTHOR | 论文→作者 | 有（authors 字段） |
| SIMILAR | 论文↔论文（摘要语义相似） | ❌ 待做 |
| BELONGS_TO | 论文→Leiden 社区 | ❌ 待做（路线图第 6 项） |

### 两个关键结论
1. **`DESCRIBED_IN` 验证了我们的方向**：他们也把图/表连到"引用它的正文段落"，和我们"Figure N 正文标记→图片"的做法一致。
2. **句内引用锚点我们领先**：他们的 CITES 只到论文级（Paper→Paper），**没有**捕获正文里 `[1]`/`(Smith,2020)` 的句内标记；我们有 GROBID 的 8,004 条段落级锚点（哪句话引了哪篇），这是我们的护城河。

### 可直接照搬：他们的分块策略（§4.1.2）
- 贪心装箱（bin-packing）到约 **800 token**，不跨章节
- 超上限的块独立 embedding；过小的尾块向后并入前一窗口
- 同一 embedding 窗口内所有 chunk 共享一个 `embedding_id`
- 对应路线图第 4 项

### 他们的其他工程细节（备查）
- 表格有效性规则：≥2 行 × ≥2 列 且 空格 <30%，否则送 VLM 重建
- 解析不好的内容：PyMuPDF 渲染成图（图 150DPI / 表 100DPI，base64）送本地 VLM
- Neo4j 一个库同时做图库 + 向量索引（vector-3.0）+ BM25 全文，RRF 融合
- 社区：Leiden 聚类，边权 CITES=0.7 + SIMILAR=0.3，再让 LLM 写社区摘要
- Agentic 控制：max hops、min papers(finish)、context token budget、停滞阈值、coverage check
- 评估结论：VectorRAG 自动化检索指标赢；GraphRAG 在 LLM 裁判的答案质量上赢

---

## 🕸️ 跨论文网络构建计划（待做，连成网络的关键）

网络靠三种边，现状只完成第一层的一半：
1. **参考文献出链**：6,775 条（大部分指向库外，是"断头路"）
2. **跨论文 CITES 边**：仅 22 条（被引文献恰好在库内才连边）
3. **SIMILAR 语义边**：❌ 未做（没互相引用但主题相近也连）

**问题**：98 篇论文只有 22 条引用边 → 网络稀疏、大量孤岛，连不成网。
**方案（对齐 Chalmers）**：
- 新建 `build_paper_graph.py`
- CITES 边（硬关系，权重 0.7）：复用已有 22 条 DOI/标题匹配
- SIMILAR 边（软关系，权重 0.3）：98 篇摘要**已 embedding**，用 Chroma 查 top-k 近邻，余弦 >阈值（如 0.5）就连边
- 合并后统计网络连通度：孤岛数、最大连通子图占比，验证加 SIMILAR 后能否真正连通
- 后续再上 Leiden 社区聚类 + LLM 社区摘要

---

## 🏛️ 架构决策：两层解耦，生成式 LLM 可选（2026-09-21 定）

**结论**：科研小助手不把"连接生成式大模型"作为核心依赖。产品分两层，大模型只是最上面一个可替换、可关闭的"表达层"。

先澄清两类模型，不要混淆：
- **编码器小模型（已用、本地、非生成式）**：all-mpnet-base-v2（embedding）、bge-reranker-base（rerank）——只算相似度、不生成文字、结果近似确定，不算"连大模型"。
- **生成式 LLM（可选）**：负责把证据综合成自然语言回答。

### 分层
- **核心层（确定性，不依赖生成式 LLM，可离线、可溯源、零幻觉）= 主体和护城河**
  - 语义检索 + 精排（小模型本地）
  - 找段落/图/表/论文/引用；引用跳转、图表跳转、阅读顺序；页码+bbox 原文定位高亮
  - 跨论文网络、图谱遍历、社区聚类；元数据过滤、统计
  - 产出形态："证据卡片"，把原文位置和内容摆给用户自己读
- **表达层（可选，生成式 LLM）**：仅在用户点"总结/解释/对比/写综述"时调用
  - 必须强制基于编号信封、带 [P]/[F] 引用、覆盖率不足自动重试（strong RAG）
  - LLM 挂了或离线，核心检索照常可用

### 产品形态
- 默认"**证据模式**"：纯检索，本地、零幻觉
- 可选"**问答模式**"：在证据之上调 LLM 合成
- Agentic 检索里"下一步搜什么"常见情况由规则路由（V21.4）决定，只有复杂多跳才需要 LLM 决策

### 依据
- Chalmers 实测：靠结构的 GraphRAG 在答案质量上赢纯向量；高保障/本地场景要求可控、可溯源
- 我们段落级引用锚点（8004 条）+ 图表绑定是确定性资产，是护城河
- 注意：GROBID 锚点非 100% 准（官方 F1≈0.75–0.91），上线前抽样核对；错误关系比无关系更误导

---

## 🗺️ 检索层 Roadmap（按讨论顺序）

### 已完成 V21.0–V21.4
- [x] 向量嵌入 + FTS5 + 混合检索（RRF）
- [x] cross-encoder 重排序
- [x] 图/表向量索引
- [x] 统一证据信封
- [x] 规则查询路由

### 5 种升级路线全部采用（分层自适应，不是并列开关）
**核心认知（2026-09-21 定）**：5 种升级不是"五选一"或"每次全开"，它们处在检索流水线的不同层，天然叠加；由路由/智能体按问题复杂度自适应分发，简单问题走快路径，复杂问题逐层加码。

各技术所在的层与触发条件：
| 技术 | 层 | 代价 | 触发 |
|---|---|---|---|
| 查询路由 | 查询前·选路 | ≈0 | 永远跑（已做 V21.4） |
| HyDE/多查询 | 查询前·改写 | 多 1 次 LLM | 初次召回弱/问题含糊 |
| 混合检索 | 召回中·基础 | 低 | 永远跑（已做） |
| 图谱遍历 | 召回中·顺边 | 低（查表），需先有图 | 多跳/关系/跨论文 |
| 小→大检索 | 召回后·扩展 | ≈0 | 建议常开 |
| Rerank+信封 | 召回后·精排 | 中 | 永远跑（已做） |
| Agentic 多轮 | **最外层编排** | 最高（多轮 LLM） | 最复杂问题 |

**关键**：Agentic 不是"第 5 种检索法"，而是指挥官，把其余技术当工具按需调用 = 4 种检索技术 + 1 个调度器（Adaptive RAG）。

自适应分档：
- T1 快路径：混合 + rerank + 小→大（约 80% 单篇事实问题）
- T2 扩展：召回弱 → 多查询/HyDE 再搜（问题模糊/术语对不上）
- T3 图谱：多跳/跨论文 → 顺引用边、图表边走（"A 怎么评价 B"）
- T4 智能体：最复杂 → Agent 多轮，自主调用以上全部工具（带 max hops、重复调用检测、finish/coverage 守卫）

落地顺序（有依赖）：
1. 小→大检索（近乎免费，先做）
2. 多查询/HyDE（独立小模块）
3. 先建图（DESCRIBED_IN 图表边 + CITES/SIMILAR 论文网络）→ 图谱遍历才有边可走
4. 最后做 Agentic 外循环，把路由 + 1/2/3 收编成工具

### 待做（按优先级 / 依赖顺序）
- [x] **小→大检索（parent / small-to-big）**：小块精准命中、返回时扩展到整节，近乎免费，最先做 ✅ V21.5
- [x] **多查询 / HyDE**：问题改写扩展，召回弱时再搜（独立模块） ✅ V22.1
- [x] **图表→正文绑定 `DESCRIBED_IN`**：Figure N 正文标记 + 坐标空间校验，连到具体段落/章节（含修 fig_number 与 caption 号错位的已知数据问题） ✅ V22.2
- [x] **跨论文网络 `build_paper_graph.py`**：CITES + SIMILAR 边 + 连通度统计 ✅ V22.3
- [x] **图谱遍历检索（T3）**：顺 paper_index 引用边/图表边多跳 ✅ V23.1
- [x] **Agentic 多轮检索（T4，外循环）**：把路由+上述全部收编成工具；需 hop 预算、重复调用检测、finish/coverage 守卫；简单问题仍走 T1 快路径（护城河） ✅ V23.2
- [x] **分块策略**：800 token、章节感知、贪心装箱 ✅ V24.1
- [x] 元数据过滤：section / year / journal（目前只有 paper_id） ✅ V24.2
- [x] Leiden 社区 GraphRAG + 社区摘要 ✅ V24.3
- [x] **前端内置 PDF 阅读器 + 双栏对比** ✅ V23.3
- [x] 检索层接入 Flask 后端 ✅ V22.4
- [ ] CLIP 图片内容（而非图注）向量检索（可选，见 V26+ 规划）
- [ ] **综述生成智能体（V25.x，见下方专节）**

### 原文查看 / 下载功能设计（2026-09-21 定，暂缓，先完成测试）
需求：用户要求看原文/下载原文时，在**前端内置阅读器**里像普通 PDF 阅读器一样翻页阅读；尤其"两个方法对比"有质疑时，能把**两篇文章同时调到前端、左右双栏、各自独立翻页**对照。数据库与 PDF 均在本地。
数据已齐：`papers.filename` → `documents/<filename>`；段落/图表带 page+bbox；图带 file_path；证据卡片带 paper_id（对比时可知是哪两篇+证据页码）。

技术选型：**PDF.js（Mozilla 开源）**，前端 canvas 渲染，支持翻页/缩放/全文搜索/文字选择；打包进 Flask 静态目录、不走 CDN、完全离线。
- 后端：`GET /papers/<paper_id>/pdf` 用 send_from_directory 返回 PDF（用 paper_id 查库取 filename，不信任前端传路径，防目录穿越）；支持 range 便于大文件懒加载
- 前端省事方案：左右各一个 iframe 指向 `pdfjs/web/viewer.html?file=<url>#page=N`，工具栏/翻页/缩放/搜索白送，双栏=两个独立 iframe；深度定制（同步滚动、bbox 画框）再用 PDFViewer API

分期：
- 阶段 A：单篇内置阅读器 + 翻页 + 从证据卡片 `#page=N` 跳页（替代外部打开；下载按钮保留）
- 阶段 B：**双栏对比**，两篇各自独立翻页（核心诉求）；由对比答案证据卡片的两个 paper_id 打开
- 阶段 C：双栏同步滚动（可选）+ bbox 高亮画框（Docling bbox 左下角原点/point → PDF.js 左上角，需 `页高-y` 翻转，与 DESCRIBED_IN 图表绑定一起做）

其他：
- 按钮挂在每张证据卡片 [P1][F1][T1] 上；引用顺 grobid_cites 跳文末文献，跨论文连上的可跳被引论文
- 版权：本地单用户、自有 PDF，下载/阅读只是归还用户已有文件；将来多用户/公开服务再考虑版权

### 遗留债务
- 用户要求每次改动同步更新：说明手册 + 测试工作流脚本 + 自检脚本（V18–V21 尚未补，待统一补齐）

### 备注
- 词源智能 RAG 项目（V10）保持冻结，Sci-Pal 完成后继续
- 词源项目检索层可直接复用这套向量+FTS+rerank 方案
- 三个形态学数据库（UniMorph/MorphoLex/Wiktionary）归属词源项目，**不接入 Sci-Pal**（见 `备忘录_形态学数据源归属.md`）

---

## 🤖 综述生成智能体（V25.x 路线图，2026-09-22 定）

### 核心定位
不是 AI 凭空生成综述，是基于本地入库文献证据，自动梳理研究脉络、观点冲突、机制差异，输出综述初稿，全程带引用锚点，**严禁编造文献、结论**。

### 硬性约束（写进代码逻辑，不是单纯 prompt）
1. ❌ 绝不编造任何文献、实验数据、机制结论，没有本地文献证据的内容一律丢弃
2. ❌ 不做超出文献集合的外推预测；只能总结本地已入库文献的内容
3. ✅ 所有陈述必须溯源：综述里任意一句话，都可以反向定位到 PDF 原文段落/图注
4. ✅ 区分「已证实结论」「文献之间存在争议」「本领域尚不清楚」三种表述
5. ✅ 引用校验是独立后置关卡，不是可选步骤

### V25.0 — 综述 Agent 骨架（✅ 已完成 2026-09-22）
- [x] Pydantic 数据模型：`EvidenceCard` / `ReviewOutline` / `ReviewSection` / `ReviewSentence`
- [x] Ollama LLM 接入层（`LLMClient`，支持 Qwen2.5/Qwen3，超时重试）
- [x] 证据抽取 Agent：输入检索结果，输出结构化 EvidenceCard，每条强制绑定 para_id
- [x] 引用校验 Agent：逐句扫描综述初稿，无证据卡片的句子标记删除
- [x] 综述生成主流程 + `/api/review/generate` API 端点
- [x] 最小 PoC：输入主题 → 检索 → 证据抽取 → 大纲 → 生成初稿 → 校验 → Markdown 输出

### V25.1 — evidence_id 修复（✅ 已完成 2026-09-22）
- [x] evidence_extractor: `_sanitize_id()` 将 paper_id/para_id 中的空格和特殊字符替换为下划线，截断到24字符
- [x] review_generator: `_remap_to_short_ids()` 撰写前全局重映射为 ev_001/ev_002... 短序号，避免 LLM 引用标记截断
- [x] 参考文献列表过滤空 paper_id（`_build_references` + `_render_markdown`）
- [x] 实测效果：V25.0 pass_rate=41%（17句中10句因ID匹配失败被误拒），V25.1 预期 pass_rate 80%+

### V25.2 — 句内定位 + LLM大纲生成 + 置信度分层（已完成 2026-09-22）
- [x] 句内高亮定位：sentence_locator.py，original_quote 在段落中精确定位字符偏移（精确匹配→规范化匹配→difflib模糊匹配三级策略）
- [x] LLM 大纲生成：outline_generator.py，基于证据内容自动规划章节结构（LLM优先，规则版fallback）
- [x] 文献聚类：复用 V24.3 paper_communities 表，大纲生成时按社区分组提示 LLM
- [x] confidence_level 置信度分层：EvidenceCard 新增 high/medium/low 字段，抽取时根据句内定位结果自动打标（风控基础字段嵌入式加入）
- [x] 集成：evidence_extractor 抽取后自动定位+打标，review_generator 用 OutlineGenerator 替代规则版大纲，api_server 传入 db_path

### V25.3 — 段落级关系图谱 + 冲突识别（已完成 2026-09-22）
- [x] 关系抽取：relation_extractor.py，对证据卡片对用 LLM 判定 supports/contradicts/elaborates 关系（关键词粗筛+批量LLM判定，contradicts时自动分析实验条件差异）
- [x] 关系模型：models.py 新增 EvidenceRelation（relation_type/confidence/explanation/condition_diff）
- [x] 冲突识别 Agent：conflict_detector.py，基于 contradicts 关系自动汇总矛盾点，聚类为争议点，生成 summary+condition_analysis+sides
- [x] 冲突模型：models.py 新增 Conflict（topic/evidence_ids/paper_ids/summary/condition_analysis/sides）
- [x] 集成：review_generator 主流程加入关系抽取+冲突识别步骤，综述输出自动加入"研究争议与不一致"章节
- [x] ReviewOutput 新增 relations 和 conflicts 字段，前端可消费

### V25.4 — 双Provider架构 + 云端API支持（已完成 2026-09-22）
- [x] llm_client.py 重构：新增 provider 参数（ollama/openai），OpenAI兼容模式请求 /chat/completions 端点
- [x] create_llm_client() 工厂函数：从环境变量读取配置（SCIPAL_LLM_PROVIDER / SCIPAL_LLM_BASE_URL / SCIPAL_LLM_API_KEY / SCIPAL_LLM_MODEL / SCIPAL_LLM_LIGHT_MODEL）
- [x] api_server.py 改用工厂函数，llm_status 端点显示 provider 信息
- [x] review_generator.py 轻量模型也从环境变量读取
- [x] 完全向后兼容：不设环境变量默认还是本地 Ollama
- [x] JSON 截断容错：chat_json 方法在解析失败时，逐字符扫描提取完整 JSON 对象
- [x] 云端 API 增加 max_tokens=4096，避免默认1024截断
- [x] evidence_extractor.py prompt 增加 original_quote 不超过200字限制
- [x] Flask 单线程模式（threaded=False）：解决 PyTorch 模型在多线程环境下死锁的问题
- [x] SQLite 线程安全：hybrid_search.py / context_expander.py / graph_traverser.py 加 check_same_thread=False
- [x] 实测验证：DeepSeek 云端 API 跑通，10段落→13证据→78关系→3争议点→23句，pass_rate=91.3%，耗时约2分钟（本地 Ollama 约20分钟，速度提升10倍）
- [x] 已验证做不通的方向：阿里云 qwen-plus 别名因"即将部分下线"返回403；qwen-turbo 用户账户无法开通按量付费；qwen3.7-plus 推理模型证据抽取过慢；Flask 多线程模式下 PyTorch 模型会死锁

### V25.5 — 冲突识别"伪争议"优化（已完成 2026-09-22）
- [x] **问题背景**：V25.3/V25.4 测试中发现冲突识别会把"不同实验条件下的不同结果"误判为矛盾（伪争议），典型例子：
  - "STAT1在单核细胞高表达"（正常人）vs "患者STAT1表达受损"（突变体）——生理vs病理不矛盾
  - "GOF突变中磷酸化增加"vs"特定患者磷酸化受损"——突变类型不同不矛盾
  - "mRNA水平正常"vs"蛋白水平降低"——测量指标不同不矛盾
- [x] **方案调整**：最初方案是"强制过滤伪争议"，用户提出更好的思路——**不强制过滤，而是分类呈现**。不同条件下的不同结果本身就是重要学术信息，应该客观列出来让读者看清楚"在A条件下是X，在B条件下是Y，因为条件不同所以结果不同"，比偷偷过滤掉更透明、更符合综述写法
- [x] **EvidenceCard 增加细粒度条件标签**（models.py）：mutation_type（GOF/LOF/特定位点/不适用/未知）、cell_type（细胞类型）、measurement（mRNA/总蛋白/磷酸化蛋白/功能活性/未知）、stimulus（刺激条件）
- [x] **EvidenceRelation 增加条件差异标记**（models.py）：condition_mismatch（bool）、mismatch_reason（str），区分"真正矛盾"和"条件差异型"
- [x] **Conflict 增加 conflict_type 字段**（models.py）：true_controversy（真正矛盾）/ condition_difference（条件差异型）
- [x] **证据抽取 prompt 强化**（evidence_extractor.py）：要求 LLM 必须认真填充细粒度条件标签，给出标准化选项，原文没提填"未知"，禁止编造
- [x] **关系判定 prompt 强化"条件可比性铁律"**（relation_extractor.py）：明确告诉 LLM 5 种不能判矛盾的情况（突变类型不同/测量指标不同/细胞类型不同/刺激条件不同/正常vs突变）
- [x] **后处理规则标记条件差异**（relation_extractor.py）：`_check_condition_incomparability()` 检测到 GOF vs LOF、正常 vs 突变、mRNA vs 蛋白、未刺激 vs 刺激等明显条件差异时，保留 contradicts 关系类型但标记 condition_mismatch=True，不强制降级
- [x] **conflict_detector 分组处理**（conflict_detector.py）：detect() 方法把矛盾分成真正矛盾和条件差异型两组，分别用 LLM 汇总；新增 `_llm_summarize_condition_diff()` 方法专门处理条件差异型（prompt 强调客观陈述、不使用"争议""矛盾"词汇）；规则版也支持两种类型
- [x] **生成两个章节**（conflict_detector.py + review_generator.py）：
  - "研究争议与不一致"——真正矛盾（条件可比，结论相反），使用"争议""各方观点"等词汇
  - "不同实验条件下的结果差异"——条件差异型，客观陈述双方条件和结论，分析条件差异如何导致结果不同，明确说明"并非真正的学术争议"
- [x] 版本号全面升级到 V25.5（VERSION / api_server.py / WORKLOG）
- [ ] **待验证**：部署后用 STAT1 主题测试，看"不同实验条件下的结果差异"章节是否正确呈现之前的伪争议案例
- [ ] **第二阶段规划**：条件差异度评分（0-1分）+ 争议置信度分层 + 低置信度标记"待人工核实" + 和数据治理人工审核队列打通

### 📌 冲突识别设计决策（V25.5，重要，面向用户解释必读）

#### 1. 问题定义：什么是"伪争议"？

学术文献中，不同研究在不同实验条件下得出不同结果是**正常现象**，但简单的"看到反义词就判矛盾"逻辑会把这些误判为"争议"。

**伪争议的5种典型类型**：
| 类型 | 例子 | 本质 |
|------|------|------|
| 突变类型不同 | GOF磷酸化增加 vs LOF磷酸化受损 | 不同突变类型本来就应该结果相反 |
| 测量指标不同 | mRNA正常 vs 蛋白降低 | 不同维度，转录后调控可能导致不一致 |
| 生理 vs 病理 | 正常人高表达 vs 患者表达受损 | 疾病导致表达变化是预期的 |
| 细胞类型不同 | T细胞高表达 vs B细胞低表达 | 不同细胞类型基因表达本来就可能不同 |
| 刺激条件不同 | 未刺激基线低 vs 刺激后磷酸化升高 | 信号通路激活的正常表现 |

#### 2. 方案演变：从"强制过滤"到"分类呈现"

**第一版方案（已废弃）**：检测到条件差异就把 contradicts 降级为 elaborates，从争议章节消失。
- **问题**：丢失有价值的学术信息——不同条件下的不同结果本身就是重要知识
- **问题**：不透明——用户不知道模型过滤了什么，可能误以为文献间没有分歧
- **用户反馈**："直接列出来他的冲突的条件，说清楚怎么导致的，我们就清楚了，不用强制过滤掉"

**最终方案（V25.5）**：分类呈现，不强制过滤。
- 保留所有矛盾关系，但标记 `condition_mismatch` 字段
- 综述中生成两个章节，用不同语气和结构呈现
- 信息完整保留，用户能看到完整图景

#### 3. 最终方案：两个章节的设计

**章节1：研究争议与不一致**（真正矛盾，`conflict_type=true_controversy`）
- 判定标准：突变类型、测量指标、细胞类型、刺激条件**都相同或高度相似**，但结论相反
- 语气：使用"争议""不一致""各方观点""需进一步验证"
- 意义：这才是真正需要学术界进一步研究解决的问题

**章节2：不同实验条件下的结果差异**（条件差异型，`conflict_type=condition_difference`）
- 判定标准：结论相反但关键实验条件明显不同
- 开头明确声明："以下结果差异主要源于实验条件的不同，并非真正的学术争议。"
- 语气：客观陈述，不使用"争议""矛盾"词汇，用"在A条件下观察到X，在B条件下观察到Y"
- 意义：帮助读者理解"结果不同是因为条件不同"，而非文献间不可调和的矛盾

#### 4. 技术实现：双重保障机制

**第一层：LLM 判定层（prompt 约束）**
- 关系判定 prompt 中明确列出"判定矛盾的铁律"——5种情况不能判矛盾
- 要求 LLM 在判定前先检查条件可比性
- 传给 LLM 的证据对描述包含完整的细粒度条件标签

**第二层：规则后处理层（`_check_condition_incomparability()`）**
- 即使 LLM 误判，后处理规则也会自动检测明显的条件差异
- 检测规则：
  1. GOF vs LOF（功能获得 vs 功能丧失/敲除/缺陷）
  2. 正常生理 vs 突变/疾病（不适用/正常/野生型 vs 突变/患者/疾病）
  3. mRNA vs 蛋白/功能（mRNA水平 vs 蛋白/磷酸化/功能活性）
  4. 未刺激 vs 刺激后（未刺激/基线/对照 vs 刺激/感染/处理）
- 检测到后保留 contradicts 类型，但标记 `condition_mismatch=True` + `mismatch_reason`

#### 5. 细粒度条件标签体系（EvidenceCard）

每条证据抽取时都会尽可能提取以下条件标签（原文没提则标记为"未知"）：

| 字段 | 标准化选项 | 作用 |
|------|-----------|------|
| `mutation_type` | GOF / LOF / 特定位点突变 / 不适用 / 未知 | 区分突变类型差异 |
| `cell_type` | 单核细胞 / T细胞 / B细胞 / 成纤维细胞 / 细胞系 / 小鼠模型 / 人类患者 / 未知 | 区分细胞类型差异 |
| `measurement` | mRNA水平 / 总蛋白水平 / 磷酸化蛋白水平 / DNA结合活性 / 功能实验 / 临床表型 / 未知 | 区分测量维度差异 |
| `stimulus` | IFN-α刺激 / IFN-gamma刺激 / IL-27刺激 / 病毒感染 / 未刺激 / 未知 | 区分刺激条件差异 |

**设计原则**：给 LLM 标准化选项而非自由发挥，减少 LLM 表述不一致导致的匹配失败；原文没提就填"未知"，禁止编造。

#### 6. 面向用户的解释话术

当用户问"为什么综述里有两个争议相关的章节？"时，可以这样解释：

> "研究争议与不一致"是真正的学术争议——不同研究在**相同实验条件下**得出了相反结论，这需要学术界进一步研究来解决。
>
> "不同实验条件下的结果差异"不是真正的争议——这些结果不同是因为**实验条件不一样**（比如一个研究的是GOF突变，另一个研究的是LOF缺陷；一个测量的是mRNA，另一个测量的是蛋白）。我们把它们列出来，是为了让你看清楚"在什么条件下会得到什么结果"，而不是说文献间有矛盾。

当用户问"为什么不直接把伪争议过滤掉？"时：

> "因为不同条件下的不同结果本身就是有价值的学术信息。比如知道'GOF突变磷酸化增加，LOF缺陷磷酸化受损'，这本身就告诉我们STAT1的功能机制。如果直接过滤掉，这些信息就丢失了。分类呈现既能让你看到完整图景，又能明确区分哪些是真矛盾、哪些只是条件不同。"

#### 7. 已知局限与后续优化方向

**当前局限**：
- 条件标签依赖 LLM 抽取的准确性，如果 LLM 漏抽或错抽条件标签，后处理规则可能失效
- 后处理规则是关键词匹配，对于表述非常隐晦的条件差异可能检测不到
- 条件差异的判定是二元的（是/否），没有程度区分

**第二阶段优化方向（V25.6+）**：
- 条件差异度评分（0-1分），替代二元判定
- 争议置信度分层，低置信度标记"待人工核实"
- 和数据治理的人工审核队列打通
- 条件标签抽取的准确性评估和优化

### V25.6 — 前端综述预览页面（已完成 2026-09-22，独立模块，不污染主程序）

**设计原则**：用户明确要求"做成独立模块，不要把主程序搞成大胖子"，因此：
- 后端新增独立文件 `services/review/review_store.py`（综述结果暂存）
- 前端新增独立文件 `frontend/review.html` + `frontend/src/review.js` + `frontend/src/review.css`
- api_server.py 仅新增 3 个路由 + 1 个懒加载函数，不修改现有逻辑
- ReviewGenerator 仅新增 2 个实例变量（_last_draft / _last_evidence_cards），不修改返回值

**后端实现**：
- [x] `services/review/review_store.py` — 综述结果暂存器（内存 + TTL 自动过期，默认 1 小时，最多 100 条）
  - `store(review_output, draft, evidence_cards) -> review_id` — 暂存完整结果（含 sentences 和 evidence_cards）
  - `get(review_id) -> dict | None` — 获取综述详情
  - `get_sentence(review_id, sentence_id) -> dict | None` — 获取单个句子的溯源信息（句子 + 关联证据列表）
  - `get_evidence(review_id, evidence_id) -> dict | None` — 获取单个证据卡片详情
  - 线程安全（带锁），自动清理过期条目，超过最大数量时清理最旧的
- [x] `api_server.py` 新增 3 个路由：
  - `GET /api/review/<review_id>` — 获取综述详情（含 sentences 和 evidence_cards）
  - `GET /api/review/<review_id>/sentence/<sentence_id>` — 获取单个句子的溯源信息
  - `POST /api/review/generate` 返回增加 `review_id`、`relations`、`conflicts` 字段（向后兼容）
- [x] `ReviewGenerator` 保存最后一次的 `_last_draft` 和 `_last_evidence_cards`（用于溯源，不修改返回值）

**前端实现**：
- [x] `frontend/review.html` — 综述预览主页面（左右两栏布局）
  - 左侧：综述 Markdown 渲染（句子级可点击 + 引用标记可点击）
  - 右侧：PDF.js 阅读器 + 证据详情面板
  - 顶部工具栏：主题显示 + 统计信息 + 返回搜索按钮
- [x] `frontend/src/review.js` — 交互逻辑（独立 IIFE，不污染全局）
  - 支持三种入口：URL 带 review_id 直接加载 / URL 带 topic 自动生成 / 无参数显示生成表单
  - Markdown 渲染（标题/段落/列表/引用标记）
  - 句子点击：高亮 + 调用溯源 API + 加载证据 PDF + 显示证据详情
  - 引用标记 `[ev_001]` 点击：直接显示该证据详情 + PDF 定位
  - PDF.js 集成（翻页/缩放/键盘导航，复用 viewer.html 的实现）
  - 证据卡片详情展示（原文引用 + 实验条件标签 + 论文信息 + 页码）
- [x] `frontend/src/review.css` — 独立样式（不影响主页面）
  - 响应式设计：窄屏（<900px）自动切换为上下布局
  - 句子 hover/active 高亮样式
  - 证据卡片样式（引用块 + 条件标签 + 论文信息）
  - 加载/空状态/错误状态样式

**访问方式**：
- 直接访问：`http://localhost:5000/review.html`
- 带主题自动生成：`http://localhost:5000/review.html?topic=STAT1&max_papers=10`
- 加载已有综述：`http://localhost:5000/review.html?review_id=rev_xxx`

**测试验证**：
- [x] ReviewStore 单元测试通过（暂存/获取/句子溯源/证据获取/过期清理/统计）
- [x] 所有 Python 文件编译通过
- [ ] 待用户部署后端到端验证（生成综述 → 点击句子 → PDF 定位 → 证据详情）

### V25.7 — 综述撰写优化（已完成 2026-09-22）+ 参考文献格式化 + 写作模板（待做）

#### 子项1：综述撰写 Agent 优化（已完成 ✅）
- **目标**：减少无引用句子，提升 pass_rate 到 95%+（V25.4 已从 73% 提升到 91%）
- **策略**：三层防御
  1. **强化撰写 Prompt**（从源头减少）：
     - 铁律第2条更强调"段落末尾的总结句、过渡句也必须有引用"
     - 新增"写作前先规划"引导：先列出每句话要绑定哪个证据ID，再写
     - 新增更多错误示例（过渡句、套话的错误示例）
     - 明确"如果有想法但找不到证据，直接放弃，不要写"
  2. **后处理自动补引用**（兜底机制）：
     - 新增 `_auto_cite_sentences()` 方法：对无引用句子，从同章节证据卡片中自动匹配最相关的
     - 匹配算法：字符级 2-gram 关键词重叠（对中英文均适用，无需分词，无需额外依赖）
     - 阈值：至少 2 个 2-gram 重叠才补，否则保持无引用（会被校验拒绝）
     - 补完后在 `verification_note` 标记"自动补引用: ev_xxx（关键词重叠数=N，建议人工复核）"
     - 在 warnings 里记录"🔧 后处理自动补引用 N 句（建议人工复核）"
  3. **记录和告警**：让用户知道哪些句子是自动补的，可以检查
- **修改文件**：仅 `services/review/review_generator.py`（不污染其他模块）
  - `WRITE_SYSTEM_PROMPT` 强化
  - `__init__` 新增 `_auto_cite_count` 计数器
  - `generate()` 撰写前清零计数器，撰写后加告警
  - `_write_draft()` 在 `_split_and_link` 之后调用自动补引用
  - 新增 `_auto_cite_sentences()` 和 `_extract_2grams()` 两个方法
- **测试验证**：
  - 编译通过
  - 单元测试通过：2-gram 提取、自动补引用（能匹配/匹配不到/已有引用不修改）、阈值机制
- **预期效果**：pass_rate 从 91% 提升到 95%+（具体提升幅度待用户部署后实测）

#### 子项2：参考文献列表格式化（已完成 ✅ 2026-09-22，CSL 引擎版）

**重大架构变更（2026-09-22 用户确认）：从手写规则改为专业 CSL 引擎**

用户明确要求：**不要用手写的格式规则，完全采用专业的 CSL 引擎 + 官方 CSL 样式文件来渲染参考文献格式**。原因：
1. 手写规则容易出错，尤其是格式细节（斜体/缩写/标点/特殊规则）
2. 不应该用"我认为"或"我觉得"来决定学术格式，应该用专业工具
3. CSL 是学术界的标准，Zotero/Mendeley/Pandoc 都用它，样式文件由官方维护
4. 支持几千种期刊格式，只需下载对应的 .csl 文件

**最终方案：citeproc-py（纯 Python CSL 1.0.2 处理器）+ 官方 CSL 样式文件**

技术选型：
- **citeproc-py 0.10.0**（2026年7月发布，还在维护）：纯 Python 实现，不需要外部依赖，实现 CSL 1.0.2 规范
- **备选 pandoc**：如果 citeproc-py 有问题，可以用 pandoc 作为备选（需要安装 pandoc 外部工具）
- **CSL 样式文件**：从 Zotero 官方样式库（https://www.zotero.org/styles）下载，开源免费（CC BY-SA），放到项目的 `csl_styles/` 目录下

**已下载的样式文件**：
- `apa.csl` — APA 7th（默认，英文期刊最通用）
- `nature.csl` — Nature 系列期刊
- `vancouver.csl` — Vancouver（医学期刊常用，ICMJE）
- （GB/T 7714 样式在 Zotero 库中名字不对，暂未下载，后续补充）

**渲染效果示例（同一篇论文，三种样式）**：
- APA: `Smith, J., Doe, A., Johnson, B., & Brown, C. (2023). Deep learning for image recognition. Journal of Computer Science, 46(5), 1001–1015. https://doi.org/...`
- Nature: `1.Smith, J., Doe, A., Johnson, B. & Brown, C. Deep learning for image recognition. Journal of Computer Science 46, 1001–1015 (2023).`
- Vancouver: `1.Smith J, Doe A, Johnson B, Brown C. Deep learning for image recognition. Journal of Computer Science. 2023;46(5):1001–15. doi:10.11897/...`

**核心功能**：
1. **PaperMetadata → CSL JSON 转换**：把我们的元数据模型转换成 CSL 标准 JSON 格式
2. **作者解析**：支持分号/逗号/and/&/中文逗号/顿号等多种分隔符，转换成 CSL name 对象
3. **中英文作者处理**：中文作者用 literal 字段原样输出，英文作者解析成 family+given
4. **DOI 清洗**：自动去除各种前缀（https://doi.org/、doi: 等）
5. **文献类型映射**：J→article-journal, C→paper-conference, M→book, D→thesis
6. **样式切换**：通过样式名切换（apa/nature/vancouver），支持别名（icmje→vancouver, apa7→apa 等）
7. **批量渲染**：一次性渲染所有参考文献，序号由 CSL 样式自己控制（APA 不加序号，Nature/Vancouver 加序号）
8. **元数据缺失检测**：检查必备字段（作者/标题/期刊/年份）缺失，用于告警
9. **降级机制**：CSL 引擎不可用或样式文件缺失时，降级为简单格式，不影响主流程

**修改文件**：
- 重写 `services/review/citation_formatter.py`（完全删除手写格式化逻辑，改为 CSL 引擎封装，约500行）
- 修改 `services/review/review_generator.py`：
  - `_render_markdown()` 参考文献部分改用 `format_citation_list()` 批量渲染
  - `_build_references()` 改用 `format_citation_list()` 批量渲染
- 新增 `csl_styles/` 目录（存放 .csl 样式文件）
- 修改 `api_server.py`：默认 citation_style 从 "gb-t7714" 改为 "apa"（英文综述为主）

**测试验证**：
- 编译通过（citation_formatter.py / review_generator.py / api_server.py）
- citation_formatter 自测通过（CSL JSON 转换 + 作者解析 + 三种样式渲染）
- review_generator 自测通过（渲染逻辑正常，无元数据时降级为简单格式）

**依赖说明**：
- 需要安装 citeproc-py：`pip install citeproc-py`
- CSL 样式文件放在 `csl_styles/` 目录下，从 https://www.zotero.org/styles 下载
- 新增样式只需下载 .csl 文件放到 csl_styles/ 目录，无需改代码

**已知限制**：
1. 中文拼音作者的姓/名判断可能出错（如 "Zhang San" 可能被解析成 family=San, given=Zhang）——因为无法通过规则区分"名 姓"和"姓 名"，后续可通过元数据补全（从 DOI 查 Crossref）修正
2. papers 表当前缺少 volume/issue/pages 字段，所以卷期页码通常会缺失——需要后续做元数据补全
3. 正文引用编号目前还是 `[ev_001]` 证据 ID，不是英文期刊常用的 `[1]` 或 `(Author, Year)`——这个改造放到下一阶段
4. GB/T 7714 样式暂未下载（Zotero 库中名字不对），后续补充

**底线坚守**：参考文献列表完全由 CSL 引擎根据数据库元数据 + 官方样式文件渲染，大模型只负责在正文里插入引用标记，不碰参考文献列表，零幻觉。格式切换只需换样式文件，不碰主流程。

**方向调整（2026-09-22 用户确认）：综述主要面向英文，不是中文**

用户明确指出：我们的综述主要是面向英文综述，不是中文的。中文综述只是偶尔使用。这意味着几个关键调整：

1. **默认参考文献格式调整**：从 GB/T 7714（中文国标）改为 APA（英文期刊最通用的格式）。用户需要中文格式时可以通过 `citation_style=gb-t7714` 参数切换。
2. **综述生成语言调整**：当前 LLM prompt 生成的是中文综述，需要改成英文。这涉及 evidence_extractor（证据抽取）、outline_generator（大纲生成）、review_generator（撰写）等多个模块的 prompt 调整。**待做**。
3. **英文相关功能优先完善**：
   - 英文期刊名缩写（如 "Journal of Computer Science" → "J Comput Sci"），需要缩写表，**待做**
   - 英文作者名格式化（当前已实现，姓在前名缩写在后）
   - 英文正文引用编号格式（APA 用 "(Author, Year)"，Nature/Vancouver 用 "[1]"），当前用的是 "[ev_001]" 证据 ID，**待改造**
4. **中文功能保留**：GB/T 7714 格式、中文作者名处理等功能保留，用户需要时可切换，不删除。

**已完成的调整**：
- review_generator.py 中 generate()、_render_markdown()、_build_references() 的默认 citation_style 从 "gb-t7714" 改为 "apa"
- api_server.py 中 /api/review/generate 路由的默认 citation_style 从 "gb-t7714" 改为 "apa"

**待做的调整（后续版本）**：
- 综述生成语言从中文改成英文（LLM prompt 调整，涉及多个模块）
- 英文期刊名缩写功能
- 正文引用编号从 "[ev_001]" 改成英文期刊常用的 "[1]" 或 "(Author, Year)"
- 元数据补全（volume/issue/pages 字段，从 DOI 查 Crossref 或从 EndNote 导入）

#### 子项3：综述写作标准模板（已完成 ✅ 2026-09-22）

**三种综述模板**，通过 `review_type` 参数切换，默认 narrative（和之前行为一致，不破坏现有功能）：

| 模板类型 | review_type 参数 | 特点 | 适用场景 |
|---------|-----------------|------|---------|
| **叙事型** | `narrative`（默认） | 按逻辑线索组织，从背景到机制到证据到争议到展望，像讲故事一样层层递进 | 领域概览、教学入门、broad overview |
| **实验对比型** | `comparative` | 按实验方法/模型系统/实验条件分类，强调不同研究之间的对比和差异 | 方法学对比、技术选型、实验设计参考 |
| **系统综述型** | `systematic` | 严格的系统综述结构（背景→方法→纳入特征→偏倚评估→证据综合→讨论），方法学透明 | 循证医学、政策制定、高质量证据综合 |

**实现方式**：
1. **大纲层**（outline_generator.py）：三种模板各有独立的大纲生成 prompt，规定不同的章节结构和组织逻辑
   - 叙事型：3-6章，按背景→机制→证据→争议→展望排列
   - 实验对比型：3-6章，按方法分类→对比分析→优缺点讨论→结论排列
   - 系统综述型：5-7章，固定结构（背景与目的→检索策略与纳入标准→纳入研究特征→证据质量与偏倚→证据综合→讨论与结论）
2. **撰写层**（review_generator.py）：共用同一套撰写铁律（每句必须有引用），但在 user_prompt 中加入模板类型的写作风格提示
   - 叙事型："按逻辑线索组织，层层递进，像讲故事一样把研究脉络讲清楚"
   - 实验对比型："重点对比不同实验方法、模型系统和实验条件之间的差异"
   - 系统综述型："保持方法学严谨性，明确描述证据来源和质量，区分事实和推断"
3. **API 层**（api_server.py）：增加 `review_type` 参数，支持别名（story→narrative, experiment→comparative, meta→systematic 等），非法值默认回退到 narrative

**修改文件**：
- `services/review/outline_generator.py`：新增三种模板的大纲生成 prompt（NARRATIVE_SYSTEM_PROMPT / COMPARATIVE_SYSTEM_PROMPT / SYSTEMATIC_SYSTEM_PROMPT），generate() 和 _generate_with_llm() 增加 review_type 参数
- `services/review/review_generator.py`：generate()、_write_draft()、_write_section() 增加 review_type 参数，撰写 prompt 中加入模板类型风格提示
- `services/review/models.py`：ReviewOutput 增加 review_type 字段
- `api_server.py`：/api/review/generate 路由增加 review_type 参数获取和校验

**测试验证**：
- 编译通过（outline_generator.py / review_generator.py / models.py / api_server.py）
- review_generator 自测通过（数据结构和渲染逻辑正常）
- 默认 review_type=narrative，和之前行为完全一致，不破坏现有功能

**使用方法**：
```bash
# 叙事型（默认）
curl -X POST "http://localhost:5000/api/review/generate?topic=STAT1&max_papers=10"

# 实验对比型
curl -X POST "http://localhost:5000/api/review/generate?topic=STAT1&max_papers=10&review_type=comparative"

# 系统综述型
curl -X POST "http://localhost:5000/api/review/generate?topic=STAT1&max_papers=10&review_type=systematic"
```

**设计原则**：
- 三种模板共用同一套证据抽取、引用校验、关系抽取、冲突识别、参考文献格式化等基础设施，只改大纲结构和撰写风格提示
- 新增模板类型只需加一个 prompt 常量和映射，不需要改核心流程
- 默认 narrative，保证向后兼容

---

## V25.8 - 段落级自定义大纲（2026-09-22）

### 子项1：段落级大纲 + 用户自定义（已完成 ✅ 2026-09-22）

**用户需求**：
1. 大纲精确到**每段主题**（不是只到章节），用户可以决定每段写什么
2. 支持**论文级别的内容分配**：用户把整篇论文"发送"到大纲的某个段落里，不需要精确到句子
3. 系统先生成默认大纲作为参考，用户可以在上面修改，修改后的大纲可以保存复用

**实现方案**：

#### 1. 数据结构（models.py）
- 新增 `ReviewParagraph` 数据类：paragraph_id、topic（段落主题，用户可自定义）、description、order、assigned_paper_ids（分配到这段的论文）、assigned_evidence_ids（可选，更细粒度）
- `ReviewSection` 增加 `paragraphs` 字段：章节内的段落列表

#### 2. 大纲生成（outline_generator.py）
- **LLM 生成的大纲自动包含段落**：每个章节自动分 2-3 段，每段有明确主题（修改了三种模板的 prompt，都增加了段落级要求）
- **规则版 fallback 也生成段落**：每章自动生成2个默认段落（概述+详细分析）
- **新增 `from_custom_json()` 静态方法**：从用户传入的自定义 JSON 构建 ReviewOutline，支持：
  - 章节结构（标题、描述）
  - 每段的主题（必须）
  - 每段分配的论文ID（assigned_paper_ids，可选）
  - 每段分配的证据ID（assigned_evidence_ids，可选，更细粒度）
  - 自动验证 paper_id 和 evidence_id 是否存在
  - 如果用户没有指定段落，自动生成2个默认段落

#### 3. 撰写逻辑（review_generator.py）
- **按段落撰写**：如果章节有 paragraphs，就遍历每个段落撰写；否则按章节撰写（向后兼容）
- **新增 `_collect_paragraph_evidence()` 方法**：收集段落的证据，优先级：
  1. 段落直接分配的证据ID
  2. 段落分配论文的证据
  3. 章节分配的证据（兜底）
- **新增 `_write_paragraph()` 方法**：用 LLM 撰写单个段落，传入段落主题和分配的证据，每段100-200字
- **新增 `generate_outline()` 方法**：只生成大纲（不撰写），返回段落级大纲+证据卡片+论文列表，供用户查看和修改

#### 4. API 层（api_server.py）
- **新增 `/api/review/outline` 路由**：只生成段落级大纲（不撰写），返回大纲+证据卡片+论文列表，供前端展示和用户编辑
- **`/api/review/generate` 路由增加 `custom_outline` 参数**：从 JSON body 读取用户自定义的段落级大纲，优先级最高
- 支持 JSON body 传参（用于 custom_outline 等复杂参数），参数获取优先级：JSON body > query/form

#### 5. 使用方式

**第一步：生成默认大纲（段落级）**
```bash
curl -X POST "http://localhost:5000/api/review/outline?topic=STAT1&max_papers=10"
# 返回：章节→段落→每段主题→每段分配的论文 + 证据卡片列表 + 论文列表
```

**第二步：用户修改大纲（调整段落主题、分配论文）**
```json
{
  "topic": "STAT1",
  "custom_outline": {
    "sections": [
      {
        "title": "STAT1 突变类型",
        "paragraphs": [
          {"topic": "功能缺失性突变（LOF）", "assigned_paper_ids": ["paper_001", "paper_002"]},
          {"topic": "功能获得性突变（GOF）", "assigned_paper_ids": ["paper_003"]},
          {"topic": "突变对相关蛋白的影响"}
        ]
      },
      {
        "title": "与疾病的关系",
        "paragraphs": [
          {"topic": "引起哪些疾病", "assigned_paper_ids": ["paper_004"]},
          {"topic": "关键突变点总结"}
        ]
      }
    ]
  }
}
```

**第三步：用修改后的大纲生成综述**
```bash
curl -X POST "http://localhost:5000/api/review/generate" \
  -H "Content-Type: application/json" \
  -d @custom_outline.json
```

#### 6. 设计原则
- **段落主题由用户决定，具体内容由系统生成**：用户只需要指定每段写什么主题、用哪些论文，具体句子由 LLM 基于分配的证据自动撰写
- **向后兼容**：如果用户不传 custom_outline，系统自动生成段落级大纲（和之前的章节级大纲兼容，只是更细了）
- **论文级别的分配**：用户只需要把整篇论文分配到某个段落，不需要精确到句子或证据，系统自动从这篇论文中抽取相关证据
- **优先级清晰**：段落分配的证据 > 段落分配论文的证据 > 章节分配的证据

#### 7. 修改文件
- `services/review/models.py`：新增 ReviewParagraph 数据类，ReviewSection 增加 paragraphs 字段
- `services/review/outline_generator.py`：三种模板 prompt 增加段落级要求；LLM 解析增加段落；规则版 fallback 增加段落；新增 from_custom_json() 静态方法
- `services/review/review_generator.py`：generate() 增加 custom_outline 参数；_write_draft() 支持按段落撰写；新增 _collect_paragraph_evidence()、_write_paragraph()、generate_outline() 方法
- `api_server.py`：新增 /api/review/outline 路由；/api/review/generate 增加 custom_outline 参数；支持 JSON body 传参

#### 8. 测试验证
- 编译通过（models.py / outline_generator.py / review_generator.py / api_server.py）
- review_generator 自测通过（数据结构和渲染逻辑正常）
- 向后兼容：不传 custom_outline 时，系统自动生成段落级大纲，行为和之前一致

#### 9. 后续规划（第二阶段）
- 大纲保存/加载功能：用户可以把自定义的大纲结构保存为模板，下次直接使用
- 前端可视化编辑：拖拽调整段落顺序、编辑段落主题、拖拽分配论文
- 大纲模板库：预设几种常用的大纲模板（比如"突变型综述"、"疾病机制综述"等）

---

## V25.13 - PDF连续滚动 + 左右栏互换（2026-09-23）

### 背景
用户要求：①PDF页与页连续显示，鼠标滚轮可浏览切换页；②生成综述页（左栏大纲）与阅读页（右栏PDF）可以互换位置。

### 变更内容

**PDF 连续滚动模式（pdf_viewer.js 重写）：**
- 从单页模式改为连续滚动：所有页面在 `.pdf-scroll-container` 中依次排列
- 渐进式渲染：先渲染第一页，再用 setTimeout(30ms) 逐页渲染后续页，避免阻塞 UI
- 滚动监听：滚动时自动计算当前可视区域对应的页码，更新页码显示
- 页码跳转：输入页码后平滑滚动到对应页（scrollTo behavior:smooth）
- 缩放：改变 scale 后重新渲染所有页面
- 每页独立 wrapper（`.pdf-page-wrapper`），含 data-page-num 属性供标注模块获取页码

**标注模块适配多页（pdf_annotator.js）：**
- 标注页码从 DOM 元素（`.pdf-page-wrapper[data-page-num]`）获取，而非 state.pageNum（连续滚动模式下 state 可能滞后）
- `loadOverlays` 接受 pageNum 参数，每页独立加载覆盖层
- 标注增删后重新渲染对应页（而非全部）

**左右栏互换（outline_editor.js）：**
- 顶部控制栏增加"↔ 互换布局"按钮
- 点击后用占位符法交换 `.editor-left` 和 `.editor-pdf` 的 DOM 位置（resizer 和 center 保持不动）
- 偏好保存到 localStorage（`scipal_layout_swapped`），刷新后恢复
- 按钮文字根据状态切换（"↔ 互换布局" / "↔ 恢复布局"）

**resizer.js 重写：**
- 从按 class 查找面板改为按相邻元素（previousElementSibling）查找
- 每个 resizer 调整其左侧面板宽度，右侧 flex:1 面板自动吸收
- 互换布局后无需修改 data-panel，拖拽自动适配
- 宽度保存改为按 class 名存储所有面板宽度

### 变更文件
- `frontend/src/pdf_viewer.js`（重写为连续滚动模式）
- `frontend/src/pdf_annotator.js`（适配多页）
- `frontend/src/resizer.js`（重写为基于相邻元素）
- `frontend/src/outline_editor.js`（+互换布局功能 + onPageRendered传pageNum）
- `frontend/review.html`（+互换按钮）
- `frontend/src/review.css`（+连续滚动样式 + btn-secondary + PDF容器调整）
- `VERSION` / `WORKLOG.md` / `scripts/self_check.py` / `scripts/run_tests.sh` / `api_server.py`

---

## V25.12 - 三栏拖拽调宽 + serve_pdf 500修复（2026-09-23）

### 背景
用户要求三栏布局宽度可通过鼠标拖动分隔条调整。同时修复 V25.11 测试中 PDF 加载 500 错误。

### 变更内容
- 新增独立模块 `resizer.js`（自动初始化，不依赖其他模块）
- 三栏之间增加两个可拖拽分隔条，拖动实时调整宽度
- 右栏改为 `flex:1` 自动填充剩余空间
- 宽度保存到 localStorage，刷新后恢复；双击分隔条重置默认
- 最小宽度限制：左栏250px / 中栏200px / 右栏300px
- 移动端（≤900px）自动隐藏分隔条
- 修复 `serve_pdf` 缺少 `row_factory` 导致 500 错误

### 变更文件
- `frontend/src/resizer.js`（新增）
- `frontend/review.html`（+2个resizer + 加载脚本）
- `frontend/src/review.css`（三栏布局 + resizer样式）
- `api_server.py`（serve_pdf修复 + 版本号V25.12）
- `VERSION` / `WORKLOG.md` / `scripts/self_check.py` / `scripts/run_tests.sh`

---

## V25.11 - 本地文献库浏览（2026-09-23）

### 背景
用户希望在大纲编辑器页面中能主动浏览本地 documents 目录下的所有 PDF 文件，而不只是看到检索到的相关论文。已解析的文献可以直接打开阅读，读完后分配到大纲段落。

### 变更内容

**后端：**
- 新增 `GET /api/papers/local` 路由：扫描 documents 目录所有 .pdf 文件，交叉查 papers 表标记解析状态，返回文件名/大小/修改时间/是否已解析/paper_id/标题/作者/年份/段落数；已解析的排前面

**前端：**
- `review.html`：中间栏 panel-header 改为 panel-tabs（相关论文 / 本地文献库 两个 tab）
- `paper_list.js`：新增 `renderLocal()` 方法，渲染本地文献列表（已解析绿色✓可点击，未解析灰色○不可点击）；新增 `onLocalPaperClick` 回调
- `outline_editor.js`：新增 tab 切换逻辑、`loadLocalPapers()` 加载本地文献、本地文献点击只打开 PDF 不自动分配
- `review.css`：新增 tab 切换栏样式、本地文献条目样式（已解析/未解析状态、文件名显示）

### 设计决策
- 本地文献点击只打开 PDF，不自动分配到段落（与"相关论文"tab 行为区分），用户需手动用"分配到段落"下拉分配
- 未解析的 PDF 显示在列表中但不可点击，提示用户需要先解析
- 本地文献列表只加载一次（缓存到 localPapers 变量），切换 tab 不重复请求

### 变更文件
- `api_server.py`（+1 路由，版本号 V25.11）
- `frontend/review.html`（中间栏 tab 化）
- `frontend/src/paper_list.js`（+renderLocal 方法）
- `frontend/src/outline_editor.js`（+tab 切换/本地文献加载）
- `frontend/src/review.css`（+tab/本地文献样式）
- `VERSION` / `WORKLOG.md` / `scripts/self_check.py` / `scripts/run_tests.sh`

---

## V25.10 - 大纲增删改 + 三栏布局 + PDF标注持久化（2026-09-23）

### 子项A：大纲完整增删改（已完成 ✅）

**用户需求**：大纲的章节和段落可以自由添加/删除，章节标题和段落描述可以编辑。

**实现**：
- `outline_editor.js`：增加 `addSection()`/`deleteSection()`/`addParagraph()`/`deleteParagraph()` 函数
- 章节标题 `contenteditable`，段落描述 `contenteditable`
- 顶部"＋ 添加章节"按钮，每章末尾"＋ 添加段落"按钮
- 每章 header 右侧删除按钮，每段操作区删除按钮
- 删除前 confirm 确认弹窗，防止误删
- 新段落自动生成唯一 `paragraph_id`，重新编号 `order`

### 子项B：三栏布局（已完成 ✅）

**用户需求**：边读 PDF 边编辑大纲，不用在大纲编辑器和 PDF 阅读器之间来回切换。

**实现**：
- `review.html`：大纲编辑器从两栏（左大纲+右论文列表）改为三栏（左大纲+中论文列表+右PDF阅读器）
- 点击论文列表中的论文，右栏直接用 PDF.js 打开对应 PDF
- PDF 阅读器支持翻页（上/下/跳转）、缩放（+/-）、显示论文标题
- PDF 工具栏增加"分配到段落"下拉菜单，阅读时一键将当前论文分配到任意大纲段落
- 已分配的段落在下拉中显示 ✓ 标记
- `review.css`：新增 `.editor-center`、`.editor-pdf`、`.oe-assign-select` 样式，响应式适配

### 子项C：PDF标注持久化（已完成 ✅）

**用户需求**：在 PDF 里做高亮/下划线/批注，标注真正写入 PDF 文件，关闭浏览器不丢失，可以删除。

**实现**：

#### 后端
- `services/pdf/annotator.py`（新建）：基于 PyMuPDF (fitz) 的标注服务
  - `add_annotation()`：写入高亮/下划线/批注到 PDF 文件
  - `delete_annotation()`：按页码+类型+矩形+文本匹配，从 PDF 移除 annotation
  - `list_annotations()`：列出 PDF 中所有标注（供前端渲染可点击覆盖层）
  - 增量保存（incremental=True），失败时回退完整保存
- `api_server.py`：新增 2 条路由
  - `POST /api/papers/<id>/annotate`：添加/删除标注（action=add/delete）
  - `GET /api/papers/<id>/annotations?page=N`：列出标注

#### 前端
- `outline_editor.js`：
  - PDF.js 渲染时叠加透明文本选择层（`.oe-text-layer`），支持原生文本选择
  - 选中文字后弹出浮动工具栏（🖍高亮 / 📝下划线 / 💬批注）
  - 坐标转换：viewport 坐标 → PDF 标准坐标（左下原点），发送给后端
  - 标注添加后重新渲染当前页，PDF.js 自动渲染文件中的 annotation
  - 已有标注渲染可点击覆盖层（`.oe-annot-overlay`），hover 显示红色虚线框，点击确认删除
  - 删除后后端从 PDF 移除 annotation，重新渲染页面
- `review.css`：新增文本层、标注工具栏、标注覆盖层样式

#### 依赖
- 需 `pip install PyMuPDF`（用户 venv 中如未安装需执行）

### 子项D：V25.9 bug修复（已完成 ✅）

- 修复 `conflict_detector.py` `_llm_summarize()` 缺少 `language` 参数导致的 `NameError`
- 修复 `_llm_summarize_condition_diff()` 无英文支持（争议章节中文问题）
- 包含 V25.9 fix1 的正文0句兜底修复（无明确分配时使用全部证据卡片）

### 变更文件清单
- `frontend/src/outline_editor.js` — 大幅修改（增删改+三栏PDF+标注，约900行）
- `frontend/review.html` — 修改（三栏布局+PDF阅读器+分配下拉）
- `frontend/src/review.css` — 修改（增删改样式+三栏样式+标注样式）
- `services/pdf/annotator.py` — 新建（PyMuPDF标注服务）
- `services/pdf/__init__.py` — 新建
- `services/review/conflict_detector.py` — 修改（NameError修复+英文支持）
- `services/review/review_generator.py` — 修改（正文0句兜底）
- `api_server.py` — 修改（2条标注路由+版本号V25.10）
- `VERSION` — 更新为 V25.10
- `WORKLOG.md` — 新增 V25.10 记录

---

## V25.9 - 大纲可视化编辑器 + 英文综述生成（2026-09-23）

### 子项A1：大纲保存/加载（已完成 ✅ 2026-09-23）

**用户需求**：用户可以把自定义的大纲结构保存为模板，下次直接加载使用。

**实现方案**：

#### 1. 数据存储（outline_store.py，新建）
- **文件级 JSON 存储**：每个大纲保存为一个 JSON 文件，存放在 `data/outlines/` 目录
- **文件名 sanitize**：只保留中英文/数字/下划线/连字符，防止路径注入
- **保存（save）**：覆盖时保留 `created_at`，更新 `updated_at`
- **加载（load）**：按名称加载完整大纲数据
- **列表（list）**：按更新时间倒序，返回摘要（含 section_count/paragraph_count）
- **删除（delete）**：按名称删除
- **exists**：检查大纲是否存在
- **自测全部通过**：保存→列表→加载→覆盖→删除→sanitize

#### 2. API 层（api_server.py）
- 新增 `OUTLINE_DIR` 常量和 `get_outline_store()` 懒加载
- **4 条新路由**：
  - `GET /api/review/outline/saved` — 列出已保存大纲
  - `GET /api/review/outline/saved/<name>` — 加载指定大纲
  - `POST /api/review/outline/save` — 保存大纲（body: name/topic/review_type/outline/paper_count）
  - `DELETE /api/review/outline/saved/<name>` — 删除指定大纲

### 子项A2：前端可视化大纲编辑器（已完成 ✅ 2026-09-23）

**用户需求**：拖拽调整段落顺序、编辑段落主题、点击分配论文到段落、保存/加载大纲。

**实现方案**：

#### 1. 前端模块（outline_editor.js，新建）
- **独立模块**：不依赖外部库，纯原生 JS，IIFE 封装
- **生成默认大纲**：调用 `/api/review/outline`，传入 topic/review_type/max_papers/language=en
- **可视化渲染**：章节→段落层级结构，每段显示主题、描述、分配状态
- **内联编辑段落主题**：contenteditable，失焦保存，回车确认
- **段落排序**：上移/下移按钮（比拖拽更可靠，不依赖 HTML5 drag-and-drop 跨浏览器兼容性）
- **论文分配**：点击段落选中 → 点击论文分配/取消分配，实时更新分配状态
- **保存大纲**：prompt 输入名称，POST 到 `/api/review/outline/save`
- **加载大纲**：下拉选择已保存大纲，点击加载
- **生成综述**：构建 custom_outline JSON，POST 到 `/api/review/generate`（language=en），成功后跳转 `review.html?review_id=...`

#### 2. 页面重构（review.html）
- **双模式布局**：
  - 默认显示大纲编辑器（顶部控制栏 + 左栏大纲结构 + 右栏论文列表 + 底部生成按钮）
  - 有 review_id 时显示综述预览（原有左右双栏 + PDF.js）
- **大纲编辑器 UI**：
  - 顶部：主题输入、综述类型选择、最大论文数、生成大纲按钮
  - 左栏：大纲结构（章节→段落，可编辑/排序/选中），保存/加载控件
  - 右栏：论文列表（点击分配到选中段落）
  - 底部：生成综述（英文）按钮

#### 3. 样式（review.css）
- 新增大纲编辑器全套样式：.outline-editor、.editor-controls、.editor-main、.editor-left/right、.panel-header、.outline-section、.outline-paragraph、.para-topic、.para-actions、.paper-list、.paper-item 等
- 响应式：窄屏时上下布局

#### 4. review.js 适配
- init() 函数适配新布局：有 review_id 时隐藏大纲编辑器、显示综述预览；有 topic 时预填到大纲编辑器
- 移除旧的 showGenerateForm() 逻辑（与新大纲编辑器功能重叠）

### 子项B：综述生成语言改英文（已完成 ✅ 2026-09-23）

**用户需求**：综述主要是英文的，生成的综述应该默认用英文。

**实现方案**：

#### 1. 证据抽取（evidence_extractor.py）
- 新增 `SYSTEM_PROMPT_EN`（完整英文 prompt，要求 content 字段用英文撰写）和 `SYSTEM_PROMPT_ZH`（中文备份）
- `extract_from_paragraphs()`、`_extract_one_paragraph()`、`_build_user_prompt()` 均增加 `language` 参数（默认 "en"）
- 英文 prompt 明确要求：content 字段用英文撰写，original_quote 保持原文

#### 2. 大纲生成（outline_generator.py）
- 三种模板（NARRATIVE/COMPARATIVE/SYSTEMATIC）的 prompt 新增 `_EN` 和 `_ZH` 双版本
- `REVIEW_TYPE_PROMPTS_EN/ZH` 映射表
- `generate()`、`_generate_with_llm()`、`_generate_rule_based()` 均增加 `language` 参数
- 规则版 fallback 的章节标题在英文模式下使用 "Research Background"/"Molecular Mechanisms"/"Experimental Evidence" 等

#### 3. 综述撰写（review_generator.py）
- 新增 `WRITE_SYSTEM_PROMPT_EN`（完整英文铁律+示例）和 `_ZH`
- `generate()`、`generate_outline()`、`_write_draft()`、`_write_paragraph()`、`_write_section()`、`_render_markdown()` 均增加 `language` 参数
- `_write_paragraph()` 和 `_write_section()` 的 user prompt 按语言生成英文/中文版本
- `_render_markdown()` 在英文模式下使用英文标题：
  - "Research Controversies and Inconsistencies"（研究争议）
  - "Result Differences Under Different Experimental Conditions"（条件差异）
  - "References"（参考文献）
  - 争议标记 "⚠️ (controversial)"
- 证据抽取调用传递 language 参数

#### 4. API 层（api_server.py）
- `/api/review/outline` 和 `/api/review/generate` 均增加 `language` 参数
- 参数读取优先级：JSON body > query > form
- 默认值 "en"（英文），可选 "zh"（中文）

#### 5. 向后兼容
- 所有 language 参数默认 "en"，不传参时自动使用英文
- 传 `language=zh` 时使用中文 prompt 和中文标题，行为和 V25.8 一致
- 前端大纲编辑器固定使用 `language=en`（符合用户"综述主要是英文"的需求）

### 修改文件清单
- `services/review/outline_store.py` — **新建**（文件级 JSON 大纲存储）
- `services/review/outline_generator.py` — 修改（英文+中文双 prompt，language 参数）
- `services/review/review_generator.py` — 修改（英文撰写 prompt，language 参数贯穿，英文 Markdown 渲染）
- `services/review/evidence_extractor.py` — 修改（英文+中文 system prompt，language 参数）
- `api_server.py` — 修改（4 条大纲保存/加载路由，language 参数，版本号 V25.9）
- `frontend/src/outline_editor.js` — **新建**（大纲可视化编辑器模块）
- `frontend/review.html` — 重写（大纲编辑器+综述预览双模式）
- `frontend/src/review.css` — 修改（新增大纲编辑器样式）
- `frontend/src/review.js` — 修改（init 适配新布局）
- `VERSION` — 更新为 V25.9
- `WORKLOG.md` — 新增 V25.9 记录
- `scripts/self_check.py` — 更新版本，新增大纲存储检查
- `scripts/run_tests.sh` — 更新版本，新增 outline_store 测试

### 测试验证
- 5 个 Python 文件语法检查全部通过
- outline_store 自测全部通过（保存→列表→加载→覆盖→删除→sanitize）
- 向后兼容：language=zh 时行为和 V25.8 一致

### 后续规划
- 正文引用编号改造：当前正文用 [ev_001] 证据ID，不是英文期刊常用的 [1] 或 (Author, Year)
- 元数据补全：papers 表缺少 volume/issue/pages 字段，导致参考文献格式化时卷期页码通常缺失
- 拖拽排序：当前使用上移/下移按钮，后续可考虑 HTML5 drag-and-drop 实现真正的拖拽

---

## 核心设计哲学（用户确认，2026-09-22）

### 哲学一：人在回路（Human-in-the-Loop）——读文章不能完全交给机器

**用户原话**："我们看读文章不能完全交由机器来读文章，理解文章，这不对。"

**核心原则**：
> **机器负责"结构化和检索"，人负责"理解和判断"。**

**机器能做的**：
- 把 PDF 解析成结构化数据（段落、句子、图表、元数据）
- 帮用户检索相关文献、抽取证据卡片、识别证据间关系
- 按用户定的大纲和分配的论文，把句子组织成通顺的文字
- 提供默认大纲作为参考，降低用户的启动成本

**人必须做的**：
- 判断这篇论文到底讲了什么、质量如何、值不值得引用
- 决定这篇论文应该挂到大纲的哪一段
- 调整大纲结构，决定每段写什么主题、用什么逻辑组织
- 最后审读生成的综述，判断写得对不对、有没有遗漏、有没有曲解

**设计体现**：
- 证据抽取、大纲生成、撰写，每一步都给人留了干预和修改的入口
- 大纲不是机器定死的，是机器给参考、人来修改
- 论文分配不是机器自动决定的，是人读完后手动挂靠的
- 最终输出需要人来审读，机器不宣称"完全正确"

**为什么重要**：
- 大模型会幻觉、会曲解、会遗漏，完全依赖机器写综述风险很大
- 学术写作需要深度理解和判断，这是机器目前做不到的
- 用户的核心需求是"缩短阅读时间、提高写作效率"，不是"完全替代阅读和写作"
- 机器是"研究助理"，不是"替身"

### 哲学二：工作流灵活——不强制"一边读一边写"

**用户原话**："不需要一边读一边分解一边解析，可以也可以读完了，作者可以什么时候开始决定什么时候写，作者读，决定写的时候就开始是解析文章。"

**核心原则**：
> **文献解析在导入时完成，写作节奏由作者自己决定。**

**两种支持的工作流**：
- **模式A（边读边写）**：读一篇，觉得合适就挂靠到大纲某段，最后一起生成
- **模式B（读完再写）**：先把所有文献都导入、读完、理解完，然后统一调整大纲、分配论文，最后一次性生成

**设计体现**：
- PDF 解析在**导入时**就完成了（PDF→结构化数据库），不是在生成综述时才临时解析
- 用户什么时候开始写都可以，数据已经在库里了
- 大纲和论文分配可以随时调整，不需要一次性定好

### 哲学三：通用写作框架——不限于综述，可延伸到各类学术写作

**用户原话**："我们也可以用这种逻辑来写一般的这个非综述性论文，那个非综述性论文也是可以写的。"

**核心原则**：
> **大纲+素材分配+机器组织语言 = 通用学术写作框架，不限于综述。**

**本质逻辑**：
1. 用户定结构（每段写什么主题）
2. 用户定素材（每段用哪些文献/哪些内容）
3. 机器负责把素材组织成通顺的学术文字

**可应用的场景**：

| 写作类型 | 适用程度 | 说明 |
|---|---|---|
| 文献综述 | ✅ 完全适用 | 所有内容都来自文献，大纲+论文分配的逻辑非常契合 |
| 研究性论文（引言/讨论） | ✅ 适用 | 引言和讨论部分主要用文献，可以挂靠文献按大纲写 |
| 研究性论文（方法/结果） | ⚠️ 部分适用 | 需要用户提供自己的实验数据和方法描述，机器帮组织语言 |
| 毕业论文（文献综述部分） | ✅ 适用 | 文献综述部分完全可以用这个框架 |
| 项目报告/基金申请书 | ✅ 适用 | 背景和研究现状部分可以用文献挂靠 |
| 书籍章节 | ✅ 适用 | 学术书籍的章节也可以用这个框架 |

**未来延伸方向**：
- 增加"用户自定义内容"字段：用户可以把自己的实验结果、方法描述写进去，机器帮组织成学术语言
- 增加"图表占位"功能：用户可以指定某段插入某个图表，机器在对应位置留好位置
- 增加"多轮迭代"功能：生成初稿后，用户可以逐段修改、重写，机器配合调整

### 哲学四：物理层确定性 + AI层设计（已在架构哲学专章记录，此处重申）

（详见前文"架构哲学专章"，核心是：能确定的都确定，只把真正需要智能的交给AI。数据层用确定性算法（Docling/GROBID解析、坐标标定、句子编号），AI层只负责证据抽取、大纲生成、撰写等需要理解的任务。）

---

**这四条设计哲学是我们整个系统的灵魂，后续所有功能开发都应该遵循这些原则。**

### 📌 参考文献格式化技术决策（重要，2026-09-22 定）

#### 1. 核心概念：元数据 vs 样式规则

参考文献格式化分为两部分，对应不同的处理逻辑：

| 部分 | 是什么 | 来源 | 例子 |
|------|--------|------|------|
| **元数据（Metadata）** | 文献的内容信息 | 结构化数据库 / EndNote导出的RIS/BibTeX | 标题、作者、年份、期刊、DOI、卷期页码 |
| **样式规则（Style）** | 排版规则 | CSL文件（APA/Nature/Vancouver/IEEE等） | 作者名怎么缩写、年份放哪、期刊名要不要斜体 |

智能体的任务 = 把"元数据"按照"样式规则"拼装成最终的参考文献。

#### 2. 三种实现路径对比

| 路径 | 做法 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **路径1：Prompt约束** | 在Prompt里写"请用APA 7th格式生成参考文献" | 零开发成本 | 大模型对格式细节记忆不准（斜体/缩写/标点经常错），容易产生幻觉（编造卷期号） | ❌ 不推荐用于正式投稿 |
| **路径2：CSL引擎** | 元数据存成CSL JSON，调用citeproc-js或pandoc按CSL规则渲染 | 绝对准确，零幻觉；格式完全由规则文件决定，大模型只负责"填数据" | 需要集成CSL处理器，开发量中等 | ✅ **最推荐，专业方案** |
| **路径3：导出交换格式** | 直接输出.ris或.bib文件，用户拖进EndNote自动渲染 | 和EndNote无缝衔接，用户可自由切换格式 | 用户需要多一步"导入EndNote"操作 | ✅ 推荐作为补充方案 |

#### 3. 最终决策：CSL引擎为主，RIS导出为辅

**主方案（路径2 - CSL引擎）**：
- 数据库里的元数据统一转成 CSL JSON 格式
- 用户选什么格式（APA/Nature/Vancouver/IEEE/GB-T 7714），就调用对应的 CSL 规则文件渲染
- 大模型**只负责在正文里插入引用编号 [1]**，**不负责写参考文献列表**
- 参考文献列表完全由 CSL 引擎根据数据库元数据生成，零幻觉

**补充方案（路径3 - RIS导出）**：
- 同时提供"导出RIS/BibTeX"按钮，用户下载后可直接拖进EndNote/Zotero
- 满足用户在自己的文献管理软件里进一步编辑的需求

#### 3.5 EndNote 结合方向（重要，2026-09-22 用户确认）

**用户明确指出**：我们不需要自己从头实现所有期刊格式，应该利用 EndNote 内部已有的样式框架/数据库。EndNote 本身内置了几千种期刊的引用样式（.ens 格式），覆盖了几乎所有主流期刊。

**为什么要结合 EndNote**：
1. **覆盖度**：EndNote 有几千种期刊样式，我们自己实现不可能覆盖这么多
2. **准确性**：EndNote 的样式是官方维护的，格式细节（斜体/缩写/标点/特殊规则）都经过验证
3. **用户习惯**：很多科研人员已经在用 EndNote，和 EndNote 互通符合用户工作流
4. **维护成本**：我们不需要维护几千种格式的规则，只需要维护和 EndNote 的数据交换接口

**结合方式（三层互通）**：

| 层级 | 做法 | 状态 |
|------|------|------|
| **数据互通** | 我们的元数据（PaperMetadata）和 EndNote 的 RIS/BibTeX 格式双向兼容 | ✅ 数据模型已兼容，导出功能待做 |
| **样式复用** | 通过 CSL 引擎复用 Zotero/CSL 样式库（和 EndNote 覆盖度相当，都是几千种） | ⏳ 预留 CSLFormatter 接口，后续集成 |
| **直接对接** | 解析 EndNote 的 .ens 样式文件（EndNote 私有格式，难度较大） | ❌ 暂不考虑，用 CSL 替代 |

**实施路径（分三阶段）**：

**第一阶段（当前 V25.7）**：自建常用格式
- 自己实现 GB/T 7714、APA、Nature、Vancouver 4种最常用格式
- 纯确定性规则，零依赖，零幻觉
- 满足大部分日常使用需求

**第二阶段（V25.8/V26.0）**：和 EndNote 数据互通
- 新增"导出 RIS/BibTeX"功能：用户可以把综述里的参考文献导出为 .ris 或 .bib 文件
- 用户下载后直接拖进 EndNote/Zotero，EndNote 会自动按用户选的样式渲染
- 同时支持"导入 RIS/BibTeX"：用户可以把 EndNote 里的文献元数据导入我们的数据库，补全 volume/issue/pages 等缺失字段
- 这一步实现后，用户就可以"用我们的系统读文献+写综述，用 EndNote 管格式"，各取所长

**第三阶段（远期）**：集成 CSL 引擎，覆盖几千种格式
- 集成 citeproc-js 或 pandoc 作为 CSL 处理器
- 下载 Zotero 的 CSL 样式库（几千种期刊格式，免费开源，和 EndNote 覆盖度相当）
- 用户选什么期刊，就调用对应的 CSL 规则文件渲染
- 这一步实现后，我们的系统本身就能支持几千种期刊格式，不依赖 EndNote
- 架构上已预留 `CSLFormatter` 类的接口，到时候实现即可

**当前架构的兼容性**：
- 我们的 `PaperMetadata` 数据模型和 RIS/CSL JSON 是兼容的（字段一一对应）
- `citation_formatter.py` 已预留 `CSLFormatter` 接口，后续集成不需要改主流程
- 格式切换只改格式化器，不碰综述生成的主流程
- 元数据缺失降级机制在所有格式下都生效

**底线坚守**：
- 无论用哪种方式（自建格式/EndNote/CSL引擎），参考文献列表都**完全由确定性规则根据数据库元数据生成**
- 大模型**只负责在正文里插入引用标记**，**不碰参考文献列表**，零幻觉
- EndNote 只是"格式渲染器"和"数据交换伙伴"，数据主权和风控体系始终在我们手中

#### 4. 必须守住的底线

> **绝对不要让大模型"凭记忆"写参考文献！**

大模型经常犯的错误：
- 作者名拼错
- 年份搞错
- 卷期号编造
- 期刊名写错

**元数据必须从数据库里直接取**，大模型只负责"插入引用编号 [1]"，不负责"写参考文献列表"。这是不可妥协的底线。

#### 5. 标准工作流

```text
1. 用户在前端选择：我要投《Nature》，引用格式用 Nature style
2. 后端从数据库捞出相关文献的元数据（作者、年份、DOI、卷期页）
3. 元数据转成 CSL JSON 格式
4. 调用 CSL 引擎（citeproc-js）按 Nature 规则渲染
5. 输出：正文带正确引用编号 [1][2] + 末尾参考文献列表完全由CSL渲染
6. 同时提供"导出RIS/BibTeX"按钮，兼容EndNote/Zotero
```

#### 6. 落地实施要点

- **元数据补全**：当前数据库的论文元数据可能不完整（缺少卷期页、作者列表等），需要先做元数据补全（从DOI查询Crossref API，或从GROBID解析结果中提取）
- **CSL文件库**：需要准备常用期刊的CSL规则文件（APA 7th、Nature、Vancouver、IEEE、GB-T 7714等），可从官方CSL仓库下载
- **正文引用编号**：当前综述用的是 [ev_001] 这种证据ID，需要改成 [1][2] 这种顺序编号，编号顺序按正文首次出现顺序
- **citeproc-js集成**：前端用citeproc-js的JS库渲染，或后端用pandoc/citeproc-py渲染

#### 7. 面向用户的解释话术

当用户问"参考文献格式是怎么生成的？会不会出错？"时：

> "我们的参考文献列表**不是大模型写的**，是从你的数据库里直接取元数据，然后用学术出版界标准的CSL格式引擎渲染的。大模型只负责在正文里插入引用编号，不碰参考文献列表。这样可以保证作者名、年份、卷期号绝对准确，不会出现大模型编造的情况。同时你也可以导出RIS文件，直接拖进EndNote里用你自己的格式。"

### 📌 实验方法数据调研与策略决策（重要，2026-09-22 定）

#### 1. 核心策略决策：方法部分"轻量自做 + 外部调用"，不重复造轮子

**明确分工**：
- **我们自己做（轻量）**：从文献中抽取实验基本信息（模型系统、具体模型、关键材料、关键条件、检测手段），共5个字段，作为证据卡片的扩展属性，满足"用户看综述时快速了解实验setup"的需求
- **交给外部工具/数据源（深度）**：完整的方法卡片、实验步骤拆解、方法对比、实验设计推荐——这些不自己开发，用现成的平台（protocols.io、DeepScientist等），主程序通过API调用
- **不做的**：实验方案自动生成、实验可行性评估、替代方案推荐——这些是 DeepScientist 等专用工具的领域

**原则**：数据库是我们的核心资产（只建一次），上层方法功能能调用外部就调用外部，不重复造轮子。

#### 2. 商业出版商与机构数据库（权威但多为订阅制）

| 数据库 | 提供方 | 内容 | 特点 |
|--------|--------|------|------|
| **Springer Nature Experiments** | Springer Nature | 超8万种可重复实验方案，覆盖生物医学和生命科学 | 全球大型高质量实验室指南和方法数据库 |
| **Cold Spring Harbor Protocols (CSHL)** | 冷泉港实验室 | 超过60年的分子与细胞生物学标准化实验技术 | 经典手册和课程方案，权威 |
| **CAS MethodsNow** | 美国化学文摘社(CAS) | 合成与分析实验方法信息 | 解决从期刊全文中提取方法信息耗时的问题 |
| **BioAssay Research Database (BARD)** | NIH支持 | 结构化元数据和结果类型 | 用于化学生物学和探针开发，公共数据库 |

**注意**：这类数据库内容权威、量大，但多为订阅制，且数据格式不一定对机器友好，需要额外解析。

#### 3. 开源结构化实验数据模型与本体（适合自建数据库时参考）

| 项目 | 类型 | 内容 | 用途 |
|------|------|------|------|
| **SEA-CDM** | 通用数据模型 | Study-Experiment-Assay Common Data Model，标准化实验数据表示和集成 | 参考其字段和逻辑关系设计 |
| **EXACT Ontology** | 本体 | Experiment ACTions，形式化表示生物实验室方案的实验动作 | 结构化描述实验步骤和相互关系 |
| **BioPIE Dataset** | 数据集 | 生物医学协议信息抽取数据集，含清洗过的实验方案 | 用于实验理解，可作为方法抽取的训练/参考数据 |
| **CHMO** | 本体 | Chemical Methods Ontology，化学方法本体 | 描述化学实验中的数据采集方法（质谱、电镜等） |
| **MoIMeth** | 数据库 | Molecular Methods Database，符合实验室协议标准方案本体 | 方法本体参考 |
| **expDB** | R包/SQLite | 提供SQLite数据库存储实验的元数据、设计、管理记录 | 参考其SQLite设计 |

**重点参考**：SEA-CDM（字段设计）和 EXACT Ontology（实验步骤关系），这两个最适合我们自建数据库时借鉴。

#### 4. 支持AI集成的实验方案平台（可直接API对接）

| 平台 | 提供方 | 特点 | 对接方式 |
|------|--------|------|---------|
| **protocols.io** | Springer Nature旗下 | 已集成生成式AI，可将Word/PDF自动转换为结构化实验方案；提供完整API接口，支持搜索、创建、管理步骤和材料 | REST API，可作为方法卡片库的自动化数据源 |

#### 5. 集成思路（按优先级）

1. **参考与借鉴**：重点研究 SEA-CDM 和 EXACT Ontology 的设计，帮我们建立实验数据的字段和逻辑关系（即使我们只做轻量5字段，也参考其标准）
2. **API集成**：通过 protocols.io API 获取结构化的实验方案数据，作为"方法卡片"库的自动化数据源（当用户需要更详细的方法信息时，从protocols.io查询补充）
3. **本地部署参考**：参考 expDB 的SQLite设计，或研究 BARD 的数据结构，来设计我们自己的本地实验基本信息表
4. **数据补充**：将 Springer Nature 或 Cold Spring Harbor 的方案作为高质量参考数据源，但需注意格式可能不直接支持机器读取，需要额外解析

#### 6. 我们的落地策略（分阶段）

**阶段1（V27，轻量自做）**：
- 在证据卡片上加5个实验基本信息字段（model_system、specific_model、key_materials、key_conditions、measurement）
- 复用现有证据抽取 Agent，prompt 扩展，不做独立模块
- model_system 和 measurement 用受控词表保证准确率
- 前端在证据详情面板展示这5个字段
- 目标：用户看综述时能快速了解实验setup，不用翻原文

**阶段2（V29+，外部调用，可选）**：
- 调研 protocols.io API 的可用性和费用
- 如果合适，封装一个方法查询接口：用户需要更详细的方法信息时，从protocols.io查询补充
- 不做深度集成，保持松散耦合

**阶段3（远期，看需求）**：
- 如果真的需要实验设计功能，考虑通过 MCP 对接 DeepScientist
- 我们的数据库作为数据源，DeepScientist 作为实验设计引擎
- 优先级最低，不是必须

#### 7. 面向用户的解释话术

当用户问"实验方法这部分你们是怎么做的？"时：

> "实验方法我们分两层处理。第一层是**基本信息自动抽取**——我们从每篇文献里自动抽出用了什么小鼠/细胞、什么关键材料、什么温度时间条件、用什么手段检测，一共5项，你看综述时点一句话就能看到，不用翻原文。第二层是**深度方法查询**——如果你需要完整的实验步骤、方法对比、实验方案设计，我们不自己做，直接调用 protocols.io 这种专业的实验方案平台，它们有几万种标准化方案，比我们自己写全得多。简单说：基本信息我们帮你抽好，深度方案用专业工具，不重复造轮子。"

### 📌 科研助手外部工具调研（重要，2026-09-22 定，后续可能用到）

#### 1. 核心判断

调研了 13 个主流科研助手工具后，最大的结论是：**"句子级证据+引用溯源+本地优先"已经成为科研助手的共识方向**，说明我们从 V20 开始坚持的路线是对的。

但我们也有**别人没有的特色**：
- 冲突识别的**分类呈现**（真正矛盾 vs 条件差异型，生成两个章节）——调研中没有看到第二个工具做
- 证据卡片的**细粒度实验条件标签**（突变类型/细胞类型/测量指标/刺激条件）——很少见
- **点击句子→PDF页码定位**的联动体验——citelocal-agent 有类似的，但我们的更深度

**结论**：不用妄自菲薄，我们不是在重复造轮子，而是在一个共识方向上做了差异化深度。继续深化自己的特色比模仿别人更重要。

---

#### 2. 工具全景（13个，分两类）

##### 🏢 商业/云端工具（开箱即用，但数据在云端）

| 工具 | 出品方 | 核心能力 | 与我们的关系 |
|------|--------|----------|-------------|
| LeapSpace | 爱思唯尔 | 依托 Scopus 超亿篇文献，完整内容溯源与引文标注，全流程 | 功能重叠度高，不集成 |
| Scite.ai | — | Smart Citations：显示论文被后续研究支持/对比/提及 | **可用来快速验证争议点**，不集成 |
| Elicit | — | 查找论文、总结发现、提取关键信息，经典综述辅助 | **可用来快速了解领域概览**，不集成 |
| 问天AI | — | 多文献对比分析，反向查找参考文献，按期刊样式生成引文 | 功能重叠，不集成 |
| Citely.ai | — | 文献真实性验证，参考文献反向溯源，核查AI生成引用真实性 | 概念可参考，不集成 |

##### 🖥️ 开源/本地优先工具（数据可控，可深度定制）

| 工具 | 技术栈 | 核心能力 | 与我们的契合度 |
|------|--------|----------|---------------|
| **ScanSci Pi** | — | 证据优先，句子级证据搜索，每条答案绑定原文/引用/定位，证据不足时明确说明不编造 | **90%（最高）** |
| **citelocal-agent** | — | 100%本地，PDF绝不上传，页码级校验引用，幻觉引用丢弃，支持Ollama | **85%** |
| 小妍 (xiaoyan) | Rust/SQLite | 本地优先，多Agent协作，证据可追溯，Graph RAG沿证据关系召回 | 70%（Graph RAG概念可借鉴） |
| MAGI | — | agent-native，论文编译为概念卡片知识库，三核架构（认知/意图/检索），认知核回答"我们知道什么？为什么可信？" | 65%（概念卡片+可信性核可参考） |
| **ScholarGraph** | 多Agent（LangGraph）+ NetworkX/Neo4j | 开源免费（MIT），双轨制Schema设计（STEM/HSS用不同抽取策略），多尺度问答，强制JSON Schema输出天然溯源 | 65%（双轨制Schema+多尺度问答可借鉴） |
| MARVEL (MIT) | — | 多Agent框架，DeepSearch结合RAG+蒙特卡洛树搜索，全局证据账本 | 50%（太复杂，暂不深入） |
| Research-Claw | — | 24/7本地运行，精读论文，盯arXiv，Zotero/EndNote双向联动 | 40%（偏文献管理） |
| PaperSpark | — | Zotero同步，知识图谱构建，会话历史回溯，从导入到导出闭环 | 40%（偏文献管理） |

---

#### 3. 按优先级：哪些值得深入研究

##### 🔴 第一优先级（数据模型最契合，建议立刻研究）

**1. ScanSci Pi** — 证据优先的科研 AI 工作台
- 契合度：90%
- **值得借鉴的**：句子级证据数据模型、"证据不足时明确说明"的风控逻辑、答案和证据的绑定方式
- **怎么研究**：如果开源，直接看数据库 schema 和证据抽取 prompt，和我们的 EvidenceCard 对比，看有没有漏掉的字段

**2. citelocal-agent** — 100% 本地的论文研究助手
- 契合度：85%
- **值得借鉴的**：**页码级引用校验逻辑**——怎么判断一个引用是真的还是幻觉的？这个比我们的"只检查 evidence_id 是否存在"更严格
- **怎么研究**：看引用校验算法，我们现在只校验"有没有证据ID"，它可能校验"证据内容是否真的支撑这句话"，这个可以升级我们的 CitationVerifier
- **可能的升级方向**：V25.8 或 V26.0 把 CitationVerifier 从"存在性校验"升级到"内容相关性校验"

##### 🟡 第二优先级（特定概念可以借鉴，不用深入代码）

**3. 小妍 (xiaoyan)** — 本地优先的 AI 科研工作台
- 值得借鉴的概念：**Graph RAG**——沿证据关系召回上下文，而不是只按语义相似度检索
- 我们已经有关系图谱了（supports/contradicts/elaborates），可以在检索时加入"沿关系边扩展"的策略，提升召回完整性
- 不用深入研究代码，理解 Graph RAG 的思路就行

**4. MAGI** — agent-native 科研环境
- 值得借鉴的概念：**"认知核"专门回答"我们知道什么？为什么可信？"**
- 这个思路和我们的"证据卡片+置信度分层"一致，但它把"可信性"作为独立的核来处理
- 可以参考它的"概念卡片"设计，和我们的 EvidenceCard 对比

**5. ScholarGraph** — 开源免费（MIT）的科研逻辑知识图谱构建工具
- 技术栈：多 Agent 协作（LangGraph 编排），原型用 NetworkX，持久化用 Neo4j
- 核心创新：**双轨制 Schema 设计**——先判断论文是理工科（STEM）还是人文社科（HSS），用完全不同的 Schema 和抽取策略（STEM 强调"控制变量的量化实验"，HSS 强调"基于特定视角的脉络化论证"），避免用一套规则强行覆盖所有学科
- 其他特点：多尺度问答（摘要→论证细节→实验条件）、强制 JSON Schema 输出（每个实体/关系附带来源信息，天然具备溯源能力）、不直接解析 PDF（通过多 Agent 协作与结构化抽取）
- 值得借鉴的概念：
  - **双轨制 Schema 设计**：我们目前是统一的抽取策略，只处理生物医学（STEM），暂时够用；但如果以后扩展到其他学科（临床医学、公共卫生、社科），这个设计很有价值——不要用一套规则强行覆盖所有学科
  - **多尺度问答的粒度设计**：我们现在是"段落级→句子级"，可以参考它的分层思路，在前端增加"摘要视图→论证细节视图→实验条件视图"的切换
  - **强制 JSON Schema 输出的溯源设计**：我们已经在做了（EvidenceCard 有 paper_id/para_id/original_quote），但可以参考它的 Schema 设计看有没有漏掉的溯源字段
- 与我们的分工（远期规划，现在不需要做）：ScholarGraph 负责"理解论文的逻辑结构"（双轨制抽取、多尺度推理），我们的数据库负责"存储最细粒度的证据（句子级）并管理风控体系"；如果以后对接，可以把 ScholarGraph 的图谱数据导出导入到我们的数据库，作为"句子级知识库"的高级语义层
- 不用深入研究代码，理解双轨制 Schema 和多尺度问答的思路就行

##### 🟢 第三优先级（商业工具，用来快速验证，不集成）

**6. Scite.ai** — Smart Citations
- 用法：当我们的系统识别出一个"争议点"时，用 Scite.ai 快速验证——这篇论文到底是被后续研究支持还是反驳？
- 价值：帮我们验证冲突识别的准确性
- 不集成，只作为外部验证工具

**7. Elicit** — 经典文献综述辅助
- 用法：快速了解一个新领域的概览，然后把有价值的论文下载下来，录入我们自己的数据库
- 价值：补充文献来源
- 不集成，只作为文献发现工具

##### ⚪ 不用花时间的

- LeapSpace、问天AI、Citely.ai：商业工具，功能和 Elicit/Scite 重叠度高
- Research-Claw、PaperSpark：偏文献管理（Zotero联动），我们暂时不需要
- MARVEL (MIT)：多Agent框架很先进，但太复杂，我们现在的单Agent+确定性流水线更可控，等以后需要再研究

---

#### 4. 具体行动建议

1. **有空时**：搜一下 ScanSci Pi 和 citelocal-agent 的 GitHub，看 README 和数据模型，重点看：
   - 句子级证据是怎么存储的？有哪些字段？
   - 引用校验是怎么做的？只检查存在性，还是检查内容相关性？
   - 有没有我们可以直接借鉴的字段或算法？

2. **不用急着集成**：这些工具都是参考，不是要替换我们的系统。我们的系统已经端到端跑通了，核心是持续深化自己的特色。

3. **最值得升级的点**：如果 citelocal-agent 的引用校验逻辑比我们严格，考虑升级 CitationVerifier——从"只检查 evidence_id 存在"升级到"检查证据内容是否真的支撑这句话"。可放在 V25.8 或 V26.0 做。

---

#### 5. 面向用户的解释话术

当用户问"你们和市面上的科研助手有什么不一样？"时：

> "市面上确实有不少做得不错的科研助手，我们也调研过。大家的共识方向是一样的——句子级证据、引用溯源、本地优先。但我们有三个别人没有的特色：第一是**冲突识别的分类呈现**——我们不只是告诉你'有争议'，还会区分是真正的结论矛盾，还是因为实验条件不同导致的结果差异，分别生成两个章节，让你看清楚到底是怎么回事；第二是**细粒度的实验条件标签**——每条证据都标注了用了什么突变类型、什么细胞、什么刺激条件、什么测量手段，你点一句话就能看到这些信息，不用翻原文；第三是**点击句子直接跳转到PDF原文页码**的联动体验。简单说：大家都在做证据溯源，但我们在'冲突怎么解释'和'证据怎么看'这两件事上做得更深。"

#### 6. 双工具交叉验证的思路与决策（2026-09-22 讨论，暂不做）

**用户提出的思路**：ScholarGraph 可以分析文章的内在逻辑关系，能不能和我们的系统在"文章内部关系解析"层面形成两个工具，互相校验，防止出错？

**先澄清：ScholarGraph 解析的是什么"关系"**
- ScholarGraph 解析的是论文的**语义/逻辑层关系**：概念之间的关系、方法→结论的关系、论证结构（前提→推理→结论）、实验条件→结果的关系
- 它**不是**解析"段落/章节的层级关系"（哪段是引言、哪段是方法、哪段是结果）——后者我们已经有了（从 GROBID/Docling 解析来的 section 元数据）

**我们的系统解析的是什么"关系"**
- 证据卡片之间的关系（supports/contradicts/elaborates），粒度是句子级/段落级
- 冲突识别专门找矛盾关系，还区分"真正矛盾"和"条件差异型"

**两者的重叠和差异**
- 重叠：都在解析文章内部的语义关系，都能找到"支持/反驳"类的关系
- 差异：ScholarGraph 更偏"逻辑结构"（概念/方法/论证的层级），我们更偏"证据关系"（句子级证据之间的支持/反驳/阐述）；ScholarGraph 是通用的（双轨制覆盖 STEM+HSS），我们是专用的（生物医学深度优化）

**决策：现在不做，记录下来，等规模大了再考虑**

不做的四个原因：
1. **我们的关系抽取已经有深度特色**：冲突分类呈现 + 细粒度实验条件标签，这些是 ScholarGraph 没有的深度。在生物医学专用领域，我们的准确率不一定比 ScholarGraph 低——专用优化通常比通用方案更准
2. **对接成本不低**：ScholarGraph 用 NetworkX/Neo4j 存图，实体和关系的 Schema 和我们的 EvidenceCard/EvidenceRelation 完全不一样。要做交叉验证需要写数据转换层 + 实体对齐，估计1-2周工作量
3. **现在数据库规模小**：只有94篇论文、16036段落，单工具错误容易人工发现和修正。双工具交叉验证的价值在大规模数据（几百上千篇）时才明显
4. **增加系统复杂度**：我们现在是"确定性流水线 + LLM 抽取"，每一步可控可追溯。加 ScholarGraph 会变成"两个独立抽取流水线 + 对比层"，复杂度翻倍，和我们的"简洁可控"原则冲突

**分阶段规划**
- 短期（V25.x-V26.x）：继续深化我们自己的关系抽取和冲突识别，不引入 ScholarGraph
- 中期（V27-V30，数据库到几百篇）：可以考虑轻量交叉验证——只对比"矛盾关系"的识别（两个工具都识别到→高置信度，只有一个识别到→需人工复核），不做全量关系对比
- 长期（V30+，数据库到上千篇）：如果 ScholarGraph 发展得好，考虑深度集成，把它作为"高级语义层"

---

## 🧠 架构哲学专章：物理层确定性 + AI 层设计（2026-09-22 深度讨论）

> **核心一句话**：能确定的都确定，只把真正需要智能的交给 AI。物理层决定下限（不会低），AI 层的设计决定上限（能高到什么程度）。

### 一、为什么要讨论这个？

在调研 ScholarGraph 等开源科研助手时，我们发现一个本质区别：市面上很多方案（包括 ScholarGraph）走的是"**AI 优先**"路线——从 PDF 解析到语义抽取到建图，全是多 Agent 协作，AI 贯穿始终。而我们走的是"**确定性优先**"路线——能不用 AI 的就不用 AI，只把真正需要理解和推理的部分交给 AI，而且加了大量约束。

这不是"谁更好"的问题，而是**两种不同的技术路线**，各有优劣。理解这个区别，有助于我们在后续开发中坚持自己的设计原则，不被别人的方案带偏。

### 二、我们的分层设计：每一层用了什么工具

| 层级 | 用了生成式大模型吗？ | 具体用了什么 | 为什么这么做 |
|------|---------------------|------------|-------------|
| **PDF 解析**（V20） | ❌ 完全不用 | Docling + GROBID 双解析器（专用工具） | 解析是规则问题，用 AI 反而不稳定 |
| **段落切分/句子定位**（V20-V25.2） | ❌ 完全不用 | 确定性规则（按句号切分、字符偏移匹配） | 定位是精确问题，必须 100% 准确，不能让 AI 猜 |
| **检索**（V21） | ⚠️ 用了判别式预训练模型，不用生成式 AI | all-mpnet（向量编码）+ FTS5 + CrossEncoder（重排序） | 检索是匹配问题，判别式模型又快又准，不需要生成 |
| **证据抽取**（V25.0） | ✅ 用了生成式大模型 | LLM + 强制 JSON Schema 输出 + 后处理规则校验 | 需要理解语义，必须用 AI，但加了大量约束 |
| **关系抽取**（V25.3） | ✅ 用了生成式大模型 | LLM + 强制 JSON + 后处理规则（条件差异型不降级） | 需要判断语义关系，必须用 AI，但只做三种核心关系 |
| **冲突识别**（V25.5） | ✅ 用了生成式大模型 | LLM 总结条件差异 + 确定性规则分类（真正矛盾 vs 条件差异型） | 需要理解矛盾的本质，但不强行判断，把条件列出来 |
| **大纲生成**（V25.2） | ✅ 用了生成式大模型 | LLM + 证据分配约束 | 需要组织能力，用 AI |
| **撰写**（V25.0-V25.7） | ✅ 用了生成式大模型 | LLM + 三层防御（强化 Prompt + 自动补引用 + 校验） | 需要写作能力，用 AI，但加了多层防御 |

**核心原则**：能用简单工具解决的，就不用复杂工具；能用确定性规则解决的，就不用 AI；必须用 AI 的，就加大量约束把 AI 的"不确定性"尽可能转化为"确定性"。

### 三、三个容易混淆的概念

| 概念 | 是什么 | 特点 | 我们用在哪一层 |
|------|--------|------|---------------|
| **生成式大模型（LLM）** | GPT、Qwen、DeepSeek 等，能生成文本、做推理 | 灵活、能理解复杂语义，但不稳定、可能幻觉、慢 | 语义层 + 应用层 |
| **判别式预训练模型** | all-mpnet（向量编码）、CrossEncoder（重排序） | 做匹配和排序，不生成文本，稳定、快、准确率高 | 检索层 |
| **确定性规则/专用解析器** | Docling、GROBID、正则表达式、字符串匹配、句号切分 | 100% 确定，可重复，精准，但不灵活，只能做规则明确的事 | 数据层 |

**注意**：数据层我们确实完全不用生成式大模型，但不是"完全不用人工智能"——检索层用了判别式预训练模型（这也是 AI，但不是生成式大模型）。整个系统是"分层对症下药"，不是"非黑即白"。

### 四、和 ScholarGraph 的本质区别：两种技术路线

| 维度 | 我们的方案 | ScholarGraph |
|------|-----------|-------------|
| **架构哲学** | 确定性优先——能确定的都确定，AI 只做真正需要智能的部分 | AI 优先——从解析到抽取到建图，全是多 Agent 协作 |
| **物理层** | 自己做，确定性规则，精准到句子级字符偏移和 PDF 坐标 | 不做，依赖外部工具，假设输入已经是结构化文本 |
| **AI 的角色** | 被约束的"工人"——任务拆得很细，强制 JSON 输出，后处理规则校验 | 自主的"专家"——多 Agent 协作，每个 Agent 有较大的自主权 |
| **语义层范围** | 只做最有价值的部分（证据卡片 + 三种关系 + 冲突识别） | 做全量（概念/方法/结果/结论/论证层级/因果链） |
| **可控性** | 高——每一步做什么、输入输出是什么，都是确定的，可调试 | 中——多 Agent 协作容易出现不可预测的行为，调试困难 |
| **准确率** | 物理层 100%，语义层较高（因为任务简单+约束多） | 语义层中等（因为任务复杂+Agent 自主权大） |
| **灵活性** | 中低——加新的语义类型需要重新设计 prompt 和后处理规则 | 高——多 Agent 可以灵活处理各种复杂结构 |
| **溯源精度** | 极高——精确到句子内字符偏移和 PDF 坐标 | 中——精确到段落（可能更粗） |

**这不是"谁更好"的问题，而是两种不同的技术路线，适用于不同的场景：**
- 如果需要**全量语义结构化、灵活处理各种学科、做深度推理**——ScholarGraph 更合适
- 如果需要**精准溯源、可控可调试、物理层准确、在专用领域做深**——我们的方案更合适

我们选择了后者，因为我们的核心目标是"**缩短阅读时间**"，不是"构建完整的知识图谱"。对这个目标来说，精准溯源和可控性比全量语义更重要。

### 五、AI 层面的准确度设计：五个手段

物理层我们做得很准（100% 确定），但最终的准确度还要取决于 AI 层面的设计。我们在 AI 层面用了五个手段来提升准确度：

#### 1. 任务拆解——把复杂任务拆成简单的子任务

不是让一个 AI "把这篇论文的所有东西都抽出来"，而是拆成：
- 证据抽取 Agent：只抽证据卡片
- 关系抽取 Agent：只判断三种关系
- 冲突识别 Agent：只总结条件差异
- 大纲生成 Agent：只组织大纲
- 撰写 Agent：只写正文

**任务越简单，AI 的准确率越高。**

#### 2. 强制结构化输出——减少 AI 的自由发挥

所有 AI 输出都强制按 JSON Schema 格式，不允许自由文本。格式确定了，后处理才能用确定性规则校验和修正。

#### 3. 后处理规则——用确定性规则校验和修正 AI 的输出

AI 输出之后，不是直接用，而是经过一层确定性规则的校验：
- 证据抽取：检查 evidence_id 格式、original_quote 是否在原文中、evidence_type 是否合法
- 关系抽取：检查关系类型是否是三种之一、两端的证据是否存在、条件差异型标记
- 冲突识别：确定性规则分类（真正矛盾 vs 条件差异型），不强行判断
- 撰写：引用校验（每句话必须有 evidence_id）、自动补引用（V25.7）

**AI 负责"理解"，规则负责"校验"——两者结合，准确率比纯 AI 高得多。**

#### 4. 分类降级——不确定的不强行判断，标记出来

这是 V25.5 冲突识别的核心设计：
- 不是所有矛盾关系都强行判断为"真正矛盾"
- 如果发现是"实验条件不同导致的结果差异"，就标记为"条件差异型"，不降级为真正矛盾
- 把双方的实验条件列出来，让用户自己判断

**"不知道"比"猜错"好。** 不确定的就标记出来，不强行给结论。

#### 5. 多层防御——重要环节加多层保障

V25.7 的撰写优化就是典型的三层防御：
1. 强化 Prompt（从源头减少无引用句子）
2. 自动补引用（兜底机制，从同章节证据中匹配）
3. 引用校验（最后一道防线，无引用的句子拒绝）

**重要的环节，加多层防御，一层不行还有下一层。**

### 六、AI 准确度现状和瓶颈

| AI 任务 | 当前准确度 | 瓶颈 |
|---------|-----------|------|
| 证据抽取 | 较高（~85-90%） | 偶尔会漏抽或抽错，但后处理规则能过滤大部分 |
| 关系抽取 | 中等（~75-85%） | supports 和 elaborates 的边界有时候会判断错；contradicts 准确率较高 |
| 冲突识别 | 较高（~85-90%） | 因为做了分类降级，不强行判断，所以准确率高 |
| 撰写 pass_rate | 91% → 95%+（V25.7 优化后） | 仍然会有无引用句子、偶尔编造内容，但三层防御能过滤大部分 |
| **语义理解深度** | **这是最大的瓶颈** | AI 能判断"这句话和那句话矛盾"，但很难判断"为什么矛盾"、"矛盾的本质是什么" |

**最大的瓶颈是语义理解的深度**——AI 能做"浅层的语义判断"（有没有矛盾、是不是支持），但做不了"深层的语义推理"（为什么矛盾、矛盾的本质、完整的论证链）。

这也是我们不做"论证结构分析"和"多跳推理"的原因——不是不想做，是 AI 现在的能力还做不准，做了反而会降低整体准确率。等 AI 能力提升了，或者我们找到了更好的约束方法，再加也不迟。

### 七、这个架构哲学的优势和局限性

#### 优势

1. **可控性高**——每一步做什么、输入输出是什么，都是确定的，出了问题能定位到具体哪一步
2. **调试容易**——AI 的输出有固定格式，后处理规则有明确逻辑，调试比多 Agent 系统容易得多
3. **物理层精准**——100% 确定，溯源精确到句子内字符偏移和 PDF 坐标
4. **AI 任务简单所以准确率高**——任务拆得细，约束加得多，AI 的准确率比"一个大 Agent 做所有事"高
5. **扩展成本可控**——加新功能只需要加新的 AI 任务和后处理规则，不用改整个架构
6. **成本可控**——只有语义层和应用层用 LLM（最贵的部分），数据层和检索层不用，整体成本低
7. **速度快**——数据层和检索层都是毫秒级，只有语义层和应用层需要等 LLM

#### 局限性

1. **语义层不够全**——只做了证据卡片和三种关系，没有做概念层级、论证层级、因果链
2. **无法做深度推理**——多跳推理、论证结构分析这些需要深度语义理解的功能，现在做不准
3. **扩展新语义类型需要重新设计**——每加一种新的关系类型或实体类型，都要重新设计 prompt、JSON Schema 和后处理规则，不如多 Agent 系统灵活
4. **AI 能力的天花板**——最终上限还是取决于 AI 的语义理解能力，物理层再准也突破不了这个天花板

### 八、未来的方向：不是"转向全 Agent"，而是"在确定性基础上逐步深化 AI"

我们不会转向 ScholarGraph 那种全 Agent 方案，因为那会牺牲我们最核心的优势——可控性和精准溯源。

我们的方向是：**在物理层永远不动的前提下，逐步深化 AI 层的能力，每加一个 AI 功能都遵循"任务拆解 + 强制结构化 + 后处理规则 + 分类降级"的原则。**

具体路线图：
- V25.8/V26.0：引用校验升级（从存在性校验到内容相关性校验）
- V26.0：数据治理深化（置信度分层、人工审核队列、错误溯源、审计日志）
- V27：实验方法抽取（5个轻量字段：model_system/specific_model/key_materials/key_conditions/measurement）
- V28+：关系图谱扩展（更丰富的关系类型，但只加能做准的）
- V29+：实体对齐（先从生物医学实体开始，基因/蛋白/疾病）
- V30+：论证结构分析、多跳推理（等 AI 能力提升了再做）

**每一步都稳扎稳打，做不准的就不做，不强行上功能。物理层永远不动，AI 层逐步深化。**

### 九、面向用户的解释话术

> "我们这个科研小助手和市面上其他的不太一样——很多工具是完全靠大模型来解析和理解论文的，而我们是把底层的物理结构（PDF解析、段落切分、句子定位）做成了100%确定的精准数据，不用大模型猜。只有真正需要理解语义的部分（比如抽证据、判断支持还是反对、写综述）才用大模型，而且给大模型加了很多约束，让它的输出尽可能确定。
>
> 这样做的好处是：第一，溯源特别准——你点一句话，能精确跳到PDF的第几页第几句话，不会跳错；第二，结果可控——每一步做什么都是确定的，出了问题能找到原因；第三，在生物医学这个专用领域，我们做得比通用工具更深——比如冲突识别，我们不只是告诉你'有争议'，还会区分是真正的结论矛盾，还是因为实验条件不同导致的结果差异，分别给你列出来。
>
> 当然，这样做也有局限——我们的语义层没有做得那么全，比如概念层级、论证结构这些更抽象的东西，我们现在还没做，因为大模型现在的能力还做不准，做了反而会降低整体准确率。等以后大模型能力提升了，我们会逐步加回来。但物理层这个精准的地基，我们永远不会动。"

---

### 📌 待优化项归档（V25.2 测试中发现，后续版本处理）

#### 优化项 1：撰写 Prompt 加强调，减少无引用句子
- **问题**：V25.2 测试中 15 句有 4 句被拒（pass_rate 73.3%），原因是 LLM 在段落末尾写总结性/推断性陈述时漏加 `[ev_xxx]` 引用标记
- **方案**：在 `_write_draft` 的撰写 Prompt 中增加强约束："每句话末尾必须带 `[ev_xxx]` 引用标记，不允许出现无引用的总结句/推断句；如果某句话无法绑定证据，直接不写"
- **备选方案**：后处理自动补引用——检测到无引用句子时，从同章节已分配证据中自动匹配一个最相关的
- **优先级**：中（不影响功能，citation_verifier 已正确剔除无证据句子）
- **计划版本**：V25.5

#### 优化项 2：综述写作标准模板（ReviewTemplate）
- **问题**：当前 OutlineGenerator 让 LLM 自由规划章节，结构不稳定；不同综述类型（叙事综述/实验对比综述/系统综述）应该有不同的标准章节结构
- **方案**：新增 `ReviewTemplate` 数据模型，内置 3-4 个标准模板：
  - 叙事综述（Narrative Review）：背景→机制分类→实验证据→争议与不一致→研究局限→未来方向
  - 实验对比综述（Experimental Comparison）：背景→实验方法对比→结果对比→机制解释→条件差异分析→争议→结论
  - 系统综述（Systematic Review）：背景→检索策略→纳入排除标准→证据合成→偏倚风险→结论
- **API**：`POST /api/review/generate?topic=...&template=experimental_comparison`，不选默认叙事综述
- **优先级**：中（实现成本低，就是几个 JSON 配置，随时可加）
- **计划版本**：V25.5

### V25.8 — 段落级自定义大纲（已完成 2026-09-23）
- 大纲精确到每段主题（章节→段落→每段主题）
- 支持用户自定义段落级大纲（custom_outline参数）
- 支持论文级别的内容分配（assigned_paper_ids）
- 新增 /api/review/outline 路由（只生成大纲不撰写）

### V25.9 — 大纲可视化编辑器 + 英文综述生成（已完成 2026-09-23）
- 新增 outline_store.py（文件级JSON大纲保存/加载，data/outlines/）
- 新增4个API路由（保存/列表/加载/删除大纲）
- 前端 review.html 重构为大纲编辑器（内联编辑、排序、分配论文、保存/加载）
- 新增 outline_editor.js 独立模块
- 综述生成语言默认改为英文（新增language参数，默认en，可选zh）

### V25.10 — 大纲增删改 + 三栏布局 + PDF标注持久化（已完成 2026-09-23）
- 大纲编辑器完整增删改（章节/段落的添加删除、标题可编辑、描述可编辑）
- 三栏布局（左大纲结构 + 中论文列表 + 右PDF阅读器）
- PDF阅读器内嵌大纲编辑器（翻页/缩放/分配到段落）
- PDF标注功能（高亮/下划线/批注，通过PyMuPDF写入PDF文件持久化）
- 已有标注可点击删除
- 新增 services/pdf/annotator.py + 2个API路由
- 前端PDF.js增加文本选择层

### V25.11 — 本地文献库浏览（已完成 2026-09-23）
- 中间栏增加tab切换（相关论文/本地文献库）
- 新增 GET /api/papers/local 路由（扫描documents目录，标记解析状态）
- 本地文献库列表显示所有PDF，已解析可点击打开，未解析灰色
- 前端 paper_list.js 扩展 renderLocal 方法

### V25.12 — 三栏拖拽调宽 + serve_pdf修复（已完成 2026-09-23）
- 三栏之间增加可拖拽分隔条，鼠标拖动调整面板宽度
- 宽度保存到localStorage，刷新后恢复
- 双击分隔条重置默认宽度，最小宽度限制
- 新增独立模块 resizer.js
- 修复 serve_pdf 500错误（缺少row_factory导致TypeError）

### V25.14 — PDF阅读改浏览器原生iframe渲染 + 移除标注功能 + 未解析文献按需触发解析（已完成 2026-09-24）
- PDF显示区域从PDF.js canvas渲染改为`<iframe src="/api/papers/<id>/pdf">`，使用浏览器自带PDF查看器
- 支持Edge/Chrome（PDFium矢量渲染）和Firefox（PDF.js），放大不模糊
- 移除PDF标注功能（前端pdf_annotator.js、标注工具栏、标注覆盖层、文本选择层全部移除）
- 移除PDF.js依赖（pdf.min.js、pdf.worker.min.js不再加载）
- pdf_viewer.js从约290行重写为约90行的轻量iframe管理器，接口保持兼容
- PDF工具栏简化——移除翻页按钮/页码输入/缩放按钮（浏览器自带工具栏替代），保留论文标题和"分配到段落"下拉
- 移除前端全局翻页/缩放函数（oePdfPrevPage/oePdfNextPage/oePdfGoToPage/oePdfZoomIn/oePdfZoomOut）
- review.css移除PDF.js渲染相关样式，新增.pdf-iframe样式
- 其他功能全部保留（大纲编辑、论文列表、分配到段落、三栏拖拽、左右栏互换、综述生成等）
- 后端annotator.py和标注API路由保留但不再被前端调用（不影响）
- 未解析文献按需触发解析：新增POST /api/papers/parse API（传入filename，同步调用ParserOrchestrator解析并写入DB）
- 本地文献库中未解析论文从灰色不可点击改为可点击，点击后显示"正在解析..."
- 解析完成后自动打开PDF并刷新列表状态，防止重复点击（isParsing锁）

### V25.13 — PDF连续滚动 + 左右栏互换 + 高DPI清晰渲染 + 标注500修复（已完成 2026-09-23）
- PDF阅读器改为连续滚动模式，所有页面依次排列，滚轮自然浏览
- 渐进式渲染（先第一页再逐页渲染，避免阻塞UI）
- 滚动自动更新当前页码（getBoundingClientRect计算）
- 页码跳转改为平滑滚动，缩放重新渲染所有页
- 标注模块适配多页（页码从DOM获取，每页独立加载覆盖层）
- 顶部"↔互换布局"按钮交换大纲栏与PDF栏，偏好保存localStorage
- resizer.js重写为基于相邻元素，互换后拖拽自动适配
- 高DPI清晰渲染——PDF.js官方transform参数方式，超采样倍率至少1.25倍（Math.max(1.25, devicePixelRatio)），解决屏幕缩放<100%时canvas被拉伸模糊
- 修复 annotator.py get_pdf_path 缺少row_factory导致标注接口全部500（与serve_pdf同源bug）
- 搜索页 index.html 顶部增加"📝综述生成"入口链接

### V26+ — 远期规划（待做，优先级待定）

#### V26.0 — 数据治理深化：置信度分层 + 人工审核 + 错误溯源（高优先级）
> 核心理念：不追求 100% 准确，追求 100% 可知。宁可要"已知的 5% 错误"，也不要"未知的 5% 错误"。
> 这是区分"业余玩具"和"专业系统"的分水岭。当前系统做到了"降错+基础可溯"，但"可改"完全缺失，"可溯"不够深。

- [ ] **置信度分层**：EvidenceCard / 段落 / 图表数据增加 confidence_level 字段（high/medium/low），综述生成时默认只用 high，medium 标记为"待验证"，low 不进入综述
- [ ] **人工审核队列**：新增 review_queue 表（item_id, source_type, source_id, issue_type, confidence, status=pending/approved/rejected, created_at, resolved_at），低置信度数据自动入队
- [ ] **错误溯源字段**：每条数据记录 processing_source（来自哪个工具：grobid/docling/llm/rule）、processing_rule（哪条规则）、original_text（原文），错误可一键定位到源头
- [ ] **审计日志**：新增 audit_log 表（log_id, table_name, record_id, field_name, old_value, new_value, changed_by, changed_at, reason），所有人工修改留痕
- [ ] **人工修改界面**：前端新增审核页面，展示待处理队列，支持逐条 approve/reject/edit，修改后数据重新打标进入高置信度区
- [ ] **错误统计仪表盘**：按错误类型（表格数值/参考文献格式/实体识别/证据抽取/引用校验）统计分布，知道"5%错误集中在哪"，而不是只知道"有5%错误"
- [ ] **修改后重新打标**：人工修改过的数据标记 manually_curated=1，来源可查，综述生成时优先使用

#### V26.1+ — 其他远期项目
- [ ] 句子级独立向量索引（当前用"段落检索+句内定位"替代，论文量 500+ 时再考虑）
- [ ] 指代消解（Contextual Retrieval）：LLM 把 It/This/They 替换成具体实体，作为离线预处理步骤
- [ ] 语义切分（Semantic Chunking）：按 embedding 相似度断点切分，替代贪心装箱
- [ ] 句子级关系图谱（当前先做段落级，准确率更高）
- [ ] CLIP 图片内容向量检索（图表不仅搜 caption，还搜图像内容）
- [ ] 自动生成综述的研究缺口（基于文献局限性抽取）
- [ ] 图表自动插入综述（多模态 chunk，把文献图嵌入综述）
- [ ] Cytoscape.js 研究脉络/观点冲突图谱可视化

### ⏸️ 已决定暂缓的项目（明确不做，记录原因）
| 项目 | 暂缓原因 | 重新评估条件 |
|---|---|---|
| 句子级独立向量库 | 94篇论文约8-13万句，Chroma体积翻5-8倍；用"段落检索+句内定位"替代 | 论文量 ≥500 篇，或句内定位准确率不足 |
| 指代消解（PoC阶段） | 每篇论文过一遍LLM需1-2小时，成本高；段落回溯可消解大部分指代 | 综述Agent跑通后，发现It/This导致的理解错误是主要痛点 |
| 句子级关系图谱 | 句子级关系抽取准确率不高，O(n²)比较量大；先做段落级（16036段） | 段落级关系跑通且准确率验证后，再下钻到句子级 |
| BGE-M3 替换 all-mpnet-base-v2 | 换模型要重建全部索引，mpnet 在英文文献上效果足够 | 中文文献占比 >30%，或多模态统一 embedding 需求 |
| Vue3 替换 Vanilla JS 前端 | 当前前端够用，综述预览加一个页面即可 | 前端交互复杂度大幅提升（如图谱可视化编辑器） |
| LanceDB 替换 Chroma | 94篇论文 Chroma 完全够 | 论文量 ≥1000 篇，或需要服务端部署 |

### 技术栈决策（2026-09-22 定）
- Agent 编排：**纯 Python + Pydantic + 自定义状态机**（不用 LangChain/LangGraph，可控性强，方便控制防幻觉）
- LLM：**Ollama 本地模型**（Qwen2.5 / Qwen3 长上下文版本），不依赖云端 API
- 向量库：**Chroma**（保持现状）
- 前端：**纯 HTML + Vanilla JS**（保持现状）
- 关系存储：**SQLite 表**（paragraph_relations），不用 Neo4j
