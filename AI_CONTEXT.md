# 项目上下文

## 项目目标

Sci-Pal 是一个本地化部署的科研文献 RAG 系统：搜索本地学术文献、按大纲章节自动检索分配论文并生成综述、RAG 学术问答、在线搜索 NCBI 并下载入库、实时对接 Protocols.io 实验方法。

## 关键文档

- **架构总览（先看这个）**：[docs/架构总览.md](docs/架构总览.md) — 整体大图、模块边界、环境约束
- **接口明细（写代码时查）**：[docs/接口明细.md](docs/接口明细.md) — 所有函数签名、参数、返回值、异常
- 当前任务：[docs/任务.md](docs/任务.md)
- 变更日志：[docs/变更日志.md](docs/变更日志.md)
- 最近工作：[docs/工作日志/2026-10.md](docs/工作日志/2026-10.md)

## 不能动的东西

- **检索层接口**：`UnifiedRetriever.retrieve()` 和 `HybridRetriever.search_papers()` 的签名不能改，新增数据源只能在内部加，对外接口不变
- **数据库结构**：`data/research.db` 的表结构（papers、paragraphs、figures、tables、evidence_cards 等）不能随意改，改动必须走 migration
- **已保存的 7 章节大纲模板**：`data/outlines/` 下的预设大纲不能删除
- **综述生成流程**：不引入关系抽取和冲突检测（那是问答功能用的），不引入多智能体架构
- **Protocols.io 对接方式**：API 实时调用，不下载到本地建库

## 测试命令

```powershell
# 自检（必跑）
python self_check.py

# 测试工作流
bash test_workflow.sh

# 语法检查
python -m py_compile api_server.py

# 启动服务
python api_server.py
```

## 环境要求

- Python 3.12（venv: `venv_sciPal_py312`）
- Ollama 本地服务（`http://localhost:11434`）
- 模型：qwen2.5:3b（轻量）、qwen2.5:7b-instruct-q4_K_M（重量，Q4量化）
- Embedding：BAAI/bge-base-en-v1.5
- Reranker：BAAI/bge-reranker-base（config.json 需手动加 `"model_type": "bert"`）
- 显卡：RTX 4060 8GB（总显存占用 ~7.2GB）

## 开发约定

- 每次修改代码后同步更新：WORK_LOG.md、test_workflow.sh、self_check.py
- 代码注释用英文
- 版本号格式：V33.x（主版本.次版本）
- Git 提交信息：`V33.x: 简要描述`
