# Sci-Pal 项目指引（给 CodeBuddy）

> 本文件是 CodeBuddy 启动时的总入口。按下面的顺序读文档，再动手改代码。
> 不要一开始就盲扫代码——先把"地图"看明白。

---

## 一、阅读顺序（必须按此顺序）

1. **`AI_CONTEXT.md`** — 项目上下文索引，3 分钟看完，知道项目是干嘛的、有哪些模块
2. **`docs/架构总览.md`** — 上帝视角：整体大图、模块边界、环境约束（不可违反）
3. **`AGENTS.md`** — 给 AI 代码助手的完整说明书：技术栈、代码规范、目录结构、开发约定
4. **`docs/架构.md`** — 详细架构：每个模块的职责、调用关系、数据流
5. **`docs/DATA_LAYER_ARCHITECTURE_V2.md`** — 数据层设计：单解析器 + 通用索引的极简架构
6. **`docs/接口明细.md`** — 写代码时查：所有公开函数的签名、参数、返回值、异常
7. **`docs/任务.md`** — 当前进行中的任务清单和优先级
8. **`docs/变更日志.md`** — 版本演进历史，最近改了什么
9. **`docs/协作约定.md`** — WorkBuddy 与 CodeBuddy 的分工、路径所有权、四拍闭环、红线（**动手前必读**）

**工作日志**：`docs/工作日志/2026-10.md`（按日期记录每天改了什么）

---

## 二、项目速览

- **是什么**：本地部署的科研文献 RAG 系统
- **核心能力**：
  - 本地文献解析（PDF → 段落/图表/参考文献）
  - 混合检索（向量 + FTS5 + RRF 融合 + Cross-Encoder Rerank + MMR）
  - 按大纲章节自动检索、分配论文、生成综述
  - RAG 学术问答（多轮对话 + NLI 防幻觉校验）
  - 在线搜索 NCBI PubMed/PMC 并下载入库
  - 实时对接 Protocols.io 实验方法（只搜不下载）
- **技术栈**：Python 3.12 + Flask + ChromaDB + Ollama（本地 LLM）+ scispacy + 原生 JS
- **当前版本**：V33.17（见 `VERSION` 文件）

---

## 三、关键路径

| 用途 | 路径 |
|------|------|
| 项目根目录 | `D:\sciPal` |
| Python 虚拟环境 | `venv_sciPal_py312\Scripts\python.exe` |
| 主数据库 | `data/research.db`（SQLite，文献元数据+段落+引用） |
| 摘要库 | `data/abstracts.db` |
| 向量库（段落） | `data/chroma/`（ChromaDB，集合：sci_pal_paragraphs） |
| 向量库（摘要） | `data/chroma_abstracts/` |
| SPECTER 微调模型 | `data/specter-finetuned/` |
| LLM 服务 | Ollama `http://localhost:11434`（qwen2.5:7b） |
| 环境变量模板 | `.env.example`（复制为 `.env` 使用） |

---

## 四、核心代码目录

```
routes/                    # Flask 路由层（ai/paper/search/writing）
services/
  search/                  # 检索核心：unified_retriever, hybrid_search, agentic_search
  qa/                     # RAG 问答：qa_service.py
  review/                 # 综述生成：outline_generator, citation_verifier, conflict_detector
  ai/                     # AI 服务：ai_service, rag_validator（防幻觉）, envelope_builder
  pdf/                    # PDF 解析：annotator.py
  query/                  # 查询处理
  writing/                # 写作服务
  data/                   # 数据版本管理
  utils/                  # 重试、结构化日志
validators/                # 校验方法（目前主要在 services/ai/rag_validator.py）
scripts/                   # 批量下载、建库、自检脚本
build_db/                  # 数据库构建脚本（独立工具集）
frontend/                  # 前端页面（原生 JS）
tests/                     # 测试
docs/                      # 所有项目文档（.md + .html 架构图）
```

---

## 五、环境约束（不可违反）

- **操作系统**：Windows 10/11，Python 3.12
- **路径处理**：统一用 `pathlib.Path`，禁止硬编码 `/` 或 `\`
- **禁止 Linux 命令/库**：`chmod`、`apt-get`、`fcntl`、`resource`、`pwd` 等
- **控制台编码**：入口脚本必须加 `sys.stdout.reconfigure(encoding='utf-8')`
- **数据库**：SQLite + ChromaDB 嵌入式，不用 MySQL/PostgreSQL
- **LLM**：Ollama 本地服务，不依赖云端 GPU

---

## 六、不要读/不要碰的目录

以下目录已在 `.gitignore` 中排除，CodeBuddy 不要扫描、不要引用：

- `venv_sciPal_py312/` — 7GB 虚拟环境
- `data/` — 运行时数据（数据库、向量库、模型、缓存）
- `__pycache__/` — Python 缓存
- `uploads/` — 用户上传的 PDF
- `documents/*.pdf`、`documents/*.png` — 源 PDF 和抽出的图
- `*.tif` — 大图原始素材
- `qwen.txt` — 本地环境变量脚本（含个人路径）

---

## 七、改代码前的约定

1. **先读 `docs/架构.md` 对应模块**，确认改动范围
2. **查 `docs/接口明细.md`**，确认函数签名是否被其他地方调用
3. **改完后同步更新**：
   - `docs/变更日志.md`（版本号倒序记录）
   - `docs/工作日志/2026-10.md`（当天做了什么）
   - 如果接口变了，更新 `docs/接口明细.md`
4. **版本号规则**：在 `VERSION` 文件和提交信息里体现，如 `V33.14: xxx`
5. **自测**：跑 `scripts/self_check.py` 确认没有破坏现有功能

---

## 八、给 CodeBuddy 的第一个任务

如果你是第一次被启动，请按以下步骤回应：

1. 读完上面"阅读顺序"里的文档
2. 用 300 字以内概括：项目核心流程是什么、有哪几个关键模块、它们怎么串联
3. 然后停下来等用户派任务，不要主动改任何代码
