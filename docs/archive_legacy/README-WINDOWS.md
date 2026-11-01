# Sci-Pal Windows 环境重建指南

> 适用于在 Windows 10/11 上从零部署 Sci-Pal（科研文献 RAG 助手，当前 V33.13）。
> 项目总说明见根目录 [`README.md`](README.md)；逐行教学版见 [WINDOWS-INSTALL-GUIDE.md](WINDOWS-INSTALL-GUIDE.md)。

---

## 一、系统要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| 操作系统 | Windows 10 64 位 | Windows 11 |
| Python | 3.10（install.bat 可检测） | 3.11 / 3.12 |
| 内存 | 8GB | 16GB+ |
| 磁盘 | 10GB（代码 + 模型 + 数据库） | 20GB+（含 PDF 与向量库） |
| GPU | 不需要（CPU 可跑，慢） | 8GB 显存（如 RTX 4060）跑本地 7B 量化模型 |

**基础运行不需要** Docker、GROBID、CUDA；用云端 API 时也不需要 Ollama。
**本地 Ollama 路线**才需要安装 Ollama 并拉取模型（见第五节）。

---

## 二、安装步骤（约 15–30 分钟）

### 第 1 步：安装 Python

1. 到 https://www.python.org/downloads/ 下载 Python 3.11 或 3.12。
2. 安装时**务必勾选 "Add Python to PATH"**。
3. cmd 执行 `python --version`，显示版本号即成功。

### 第 2 步：取得代码

从 Gitee 克隆或解压代码包到无中文、无空格的路径，例如 `D:\sciPal\`：

```cmd
git clone https://gitee.com/williamsucas/sci-pal.git D:\sciPal
cd /d D:\sciPal
```

### 第 3 步：一键安装环境

双击 `install.bat`，脚本会：创建虚拟环境 `venv_sciPal` → 激活 → 升级 pip → 按 `requirements.txt` 安装依赖。

> **Docling 编译报错**：先装 Visual Studio Build Tools（勾选 "Desktop development with C++"），重启后再运行 `install.bat`。仅使用已有数据库跑检索/问答时，可不装 Docling。

### 第 4 步：恢复数据（有旧机备份时）

把旧机文件拷到对应位置：

| 旧机路径 | Windows 目标 | 重要性 |
|----------|--------------|--------|
| `data/research.db` | `D:\sciPal\data\research.db` | ⭐⭐⭐ 必须 |
| `data/abstracts.db` | `D:\sciPal\data\abstracts.db` | ⭐⭐ 摘要库 |
| `data/chroma/`（整个文件夹） | `D:\sciPal\data\chroma\` | ⭐⭐⭐ 全文向量 |
| `data/chroma_abstracts/` | `D:\sciPal\data\chroma_abstracts\` | ⭐⭐ 摘要向量 |
| `documents/`（PDF） | `D:\sciPal\documents\` | ⭐⭐ 建议 |
| `data/outlines/` | `D:\sciPal\data\outlines\` | ⭐ 可选（7 章节模板勿删） |
| `.env` | `D:\sciPal\.env` | ⭐ 可选 |

无备份见第六节"从零建库"。

### 第 5 步：配置 LLM（二选一）

复制 `.env.example` 为 `.env`，或直接在环境变量 / `start.bat` 中设置。

**路线 A：本地 Ollama（推荐，V33.9 双模型）**

```bat
set SCIPAL_LLM_PROVIDER=ollama
set SCIPAL_LLM_HOST=http://localhost:11434
set SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
set SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b
```

先安装 Ollama 并拉取模型：

```cmd
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b-instruct-q4_K_M
```

**路线 B：OpenAI 兼容云端（DeepSeek / 通义 DashScope / OpenAI）**

```bat
set SCIPAL_LLM_PROVIDER=openai
set SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
set SCIPAL_LLM_API_KEY=你的key
set SCIPAL_LLM_MODEL=deepseek-chat
```

> 当前 `start.bat` 内置默认走 openai/deepseek；切到本地 Ollama 只需把 `SCIPAL_LLM_PROVIDER` 改为 `ollama` 并补上 host/模型名，无需改代码。

### 第 6 步：在线检索可选配置（不用可跳过）

```bat
set SCIPAL_PROTOCOLS_IO_TOKEN=your_protocols_io_token
```

- **NCBI PubMed/PMC**：`online_search.py` 当前使用内置默认 email/api_key 常量，**暂未从环境变量读取**，无需配置即可用（仅限流更低）；内置密钥不要提交进仓库。
- **Protocols.io**：需在 https://www.protocols.io/developers 激活并取 Token，设置 `SCIPAL_PROTOCOLS_IO_TOKEN` 后启用；`SCIPAL_PROTOCOLS_IO_ENABLED=false` 可关闭。

### 第 7 步：启动

双击 `start.bat`，或 cmd 中：

```cmd
venv_sciPal\Scripts\activate
python api_server.py
```

浏览器打开 `http://127.0.0.1:5000`。页面加载出论文列表即成功。

---

## 三、日常使用

| 操作 | 方法 |
|------|------|
| 启动服务 | 双击 `start.bat` 或 `python api_server.py` |
| 停止服务 | cmd 窗口 `Ctrl+C` |
| 重装依赖 | 双击 `install.bat` |
| 自检 | `python self_check.py` |
| 测试工作流 | `bash test_workflow.sh`（Git Bash） |
| 页面 | 检索 `index.html` · 综述 `review.html` · 问答 `qa.html` · PDF `viewer.html` · 任务 `tasks.html` |

---

## 四、常见问题

**Q1 启动报 `No module named xxx`**：依赖没装全，重新运行 `install.bat`。

**Q2 模型加载 / Connection failed**：本地路线先确认 Ollama 已启动（`http://localhost:11434`）；向量库丢失时删除 `data/chroma/` 后重建索引（见第六节）。

**Q3 云端问答报 400**：核对 `SCIPAL_LLM_BASE_URL`、`SCIPAL_LLM_MODEL` 与 API Key 是否匹配服务商。

**Q4 浏览器空白**：刷新，查看 cmd 报错与浏览器 F12 控制台，确认 `frontend/` 存在。

**Q5 PowerShell 禁止运行脚本**：改用 cmd，或执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后选 Y。

**Q6 8GB 显存爆显存**：重量模型必须用 Q4 量化版 `qwen2.5:7b-instruct-q4_K_M`，勿用 FP16；Embedding 用 `bge-base-en-v1.5`，Reranker `config.json` 需含 `"model_type": "bert"`。

**Q7 Windows 控制台乱码/Emoji 异常**：脚本已强制 UTF-8（`chcp 65001` + `PYTHONIOENCODING=utf-8`），确保用新版终端。

---

## 五、本地模型与显存（V33.9）

| 模型 | 用途 | 约显存 |
|------|------|--------|
| `qwen2.5:3b` | 大纲、证据抽取、引用验证（轻） | ~2GB |
| `qwen2.5:7b-instruct-q4_K_M` | 写综述、问答（重，Q4） | ~4.5GB |
| `BAAI/bge-base-en-v1.5` | Embedding | ~1.5GB |
| `BAAI/bge-reranker-base` | Rerank | ~1.2GB |
| **合计** | | **~7.2GB / 8GB** |

模型可放本地路径，避免联网下载；Reranker 缺 `model_type: bert` 会报 "Unrecognized model"。

---

## 六、从零建库（无备份时）

### 6.1 准备数据

- 本地 PDF 放入 `documents/`；或用下载脚本在线获取（见 6.3）。

### 6.2 解析与建索引（已有 PDF 时）

```cmd
venv_sciPal\Scripts\activate
python -m build_db.build_database
python -m build_db.build_embeddings
python -m build_db.build_fts
python -m build_db.build_paper_graph --apply
```

首次会下载 Embedding `bge-base-en-v1.5` 与 Reranker `bge-reranker-base`。

### 6.3 在线扩充数据源（第三层本地建库）

| 脚本 | 作用 |
|------|------|
| `download_pubmed_abstracts.py` | PubMed 摘要批量下载，建摘要库 |
| `download_pmc_xml.py` / `batch_download_pmc.py` | PMC 全文 JATS XML，过滤只有摘要的文章，增量下载 |
| `download_openalex.py` | OpenAlex 2 亿+ 论文元数据/摘要，断点续传 |
| `download_protocols.py` | 实验方法（Protocol）专刊批量下载 |
| `download_bioinformatics_methods.py` | Dockstore/bio.tools/nf-core 实时方法元数据（不建向量库） |

### 6.4 自检

```cmd
python self_check.py
```

通过后即可启动。

---

## 七、目录速览

```
D:\sciPal\
├── api_server.py          # Flask 主入口（端口 5000）
├── start.bat / install.bat
├── requirements.txt / .env.example
├── AGENTS.md / AI_CONTEXT.md / ARCHITECTURE.json
├── services\              # search / review / qa / ai / pdf / data / utils
├── frontend\             # 原生 JS 页面
├── build_db\             # 离线建库脚本
├── download_*.py         # 各数据源下载脚本
├── docs\                 # 架构/接口/变更日志/架构图
├── data\                 # research.db / abstracts.db / chroma（不入库）
└── documents\            # PDF 源文件
```

遇到本文档未覆盖的问题，先看 cmd 报错、`self_check.py` 结果与浏览器 F12 控制台。
