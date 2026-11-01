# Sci-Pal Windows 安装手册（逐行详解版）

> 当前版本基线 V33.13。本文档把安装过程拆成最小步骤，每一行命令都解释清楚在干什么。
> 适合没有 Windows 开发经验的用户；快速版见 [README-WINDOWS.md](README-WINDOWS.md)。

---

## 先理解三个概念

### 1. 什么是虚拟环境（venv）？

**问题**：你电脑上可能装了很多 Python 项目，每个项目需要的包版本不一样。如果 A 项目要 `flask 2.0`，B 项目要 `flask 3.0`，装在一起就会冲突。

**解决**：虚拟环境就是给每个项目一个"独立的小房间"，房间里装的包只给这个项目用，互不干扰。

```
你的电脑
├── 全局 Python（系统自带，尽量别动它）
├── 项目A的 venv（装了 flask 2.0）
├── 项目B的 venv（装了 flask 3.0）
└── Sci-Pal 的 venv（装了我们需要的所有包）
```

**创建命令**：`python -m venv venv_sciPal`
- `python`：调用 Python
- `-m venv`：用 Python 自带的 venv 模块
- `venv_sciPal`：虚拟环境的文件夹名字（可以随便起，我们用这个）

执行后会在当前目录生成一个 `venv_sciPal/` 文件夹，里面有一份独立的 Python 解释器和包目录。

### 2. 什么是"激活"虚拟环境？

虚拟环境创建后，你需要"进入"这个房间，之后装的包才会装到这个房间里。

**Windows 激活命令**：`venv_sciPal\Scripts\activate.bat`
- `venv_sciPal\Scripts\`：虚拟环境里的脚本目录
- `activate.bat`：激活脚本

激活成功后，命令行前面会出现 `(venv_sciPal)`，表示你现在在这个房间里。

> Linux/Mac 上是 `source venv/bin/activate`，Windows 上是 `venv_sciPal\Scripts\activate.bat`，区别只是路径分隔符和脚本后缀，作用完全一样。

### 3. 什么是 pip？

`pip` 是 Python 的包管理器，相当于"应用商店"。你告诉它要装什么包，它自动去网上下载安装。

```
pip install flask        # 装 flask
pip install -r requirements.txt   # 按照 requirements.txt 里的清单批量装
pip list                 # 看当前环境装了哪些包
```

---

## 手动安装步骤（一步步来，每步都解释）

### 第1步：装 Python

**做什么**：从 python.org 下载安装 Python 3.11 或 3.12

**为什么**：我们的代码是 Python 写的，需要 Python 解释器才能跑

**注意**：
- 安装时**必须勾选 "Add Python to PATH"**
  - PATH 是 Windows 的一个环境变量，里面记录了"去哪里找可执行程序"
  - 不勾的话，cmd 里输入 `python` 会提示"不是内部或外部命令"
  - 因为 Windows 不知道 python.exe 在哪
- 装完后打开 cmd，输入 `python --version`，显示 `Python 3.11.x` 或 `3.12.x` 就成功了

### 第2步：打开 cmd，进入项目目录

**做什么**：
```cmd
D:
cd D:\sciPal
```

**解释**：
- `D:`：切换到 D 盘（如果你解压到 C 盘就不用这步）
- `cd D:\sciPal`：进入项目目录（cd = change directory）
- 之后所有命令都在这个目录下执行

### 第3步：创建虚拟环境

**做什么**：
```cmd
python -m venv venv_sciPal
```

**解释**：
- 用全局 Python 创建一个叫 `venv_sciPal` 的虚拟环境
- 执行完会多一个 `venv_sciPal/` 文件夹，里面有：
  - `Scripts/`：可执行脚本（python.exe、pip.exe、activate.bat）
  - `Lib/site-packages/`：这个环境装的包都放在这里

**验证**：输入 `dir venv_sciPal`，能看到文件夹结构就成功了。

### 第4步：激活虚拟环境

**做什么**：
```cmd
venv_sciPal\Scripts\activate.bat
```

**解释**：
- 运行激活脚本，进入虚拟环境
- 成功后命令行前面变成 `(venv_sciPal) D:\sciPal>`

**验证**：输入 `where python`，第一行应该是 `D:\sciPal\venv_sciPal\Scripts\python.exe`，说明现在用的是虚拟环境里的 Python，不是全局的。

### 第5步：升级 pip

**做什么**：
```cmd
python -m pip install --upgrade pip
```

**解释**：
- 虚拟环境里自带的 pip 可能版本旧，升级一下避免安装时报奇怪的错
- `--upgrade`：升级到最新版
- `-q`：安静模式，少输出点日志（可选）

### 第6步：安装依赖（核心步骤）

**做什么**：
```cmd
pip install -r requirements.txt
```

**解释**：
- `-r requirements.txt`：按照 requirements.txt 里的清单批量安装
- 这一步会下载并安装 20 个左右的包，加上它们的依赖（总共可能 100+ 个包）
- 首次安装约 5-15 分钟，取决于网速

**每个包是干什么的**：

| 包名 | 作用 | 为什么需要 |
|------|------|-----------|
| Flask | Web 框架 | 提供网页服务和 API 接口 |
| flask-cors | 跨域支持 | 前端 JS 调用后端 API 时需要 |
| Werkzeug | Flask 的底层依赖 | Flask 自动需要 |
| chromadb | 向量数据库 | 存储段落/摘要向量，做语义检索（规模以本地库为准） |
| sentence-transformers | 文本转向量 | 用 BAAI/bge-base-en-v1.5 把段落文字变成向量；另装 bge-reranker-base 做重排 |
| PyMuPDF | PDF 处理 | 读取 PDF 页面、提取元数据 |
| requests | HTTP 请求 | 调用 LLM API、查询 NCBI/Protocols.io 等在线服务 |
| pydantic | 数据验证 | 确保 API 返回的数据格式正确 |
| networkx | 图谱算法 | 计算论文引用网络、社区发现 |
| tqdm | 进度条 | 建库时显示进度 |
| python-dotenv | 环境变量加载 | 读取 .env 配置文件 |
| pyarrow | 列式数据 | chromadb 和 docling 的底层依赖 |
| docling | PDF 全要素解析 | 重新建库时解析 PDF 文本/图/表/公式 |
| docling-core | docling 核心 | docling 的依赖 |
| pypdf | PDF 解析（备用） | 某些 PDF 格式需要 |
| pdfplumber | PDF 表格提取 | 备用解析器 |
| PyYAML | YAML 解析 | 读取配置文件 |
| rich | 终端美化 | 自检脚本的彩色输出 |
| typer | CLI 框架 | 命令行脚本参数解析 |

**sentence-transformers 会自动附带安装**：
- torch（PyTorch，深度学习框架，约 200MB）
- transformers（HuggingFace 模型加载）
- numpy（数值计算）
- scikit-learn（机器学习工具）
- huggingface-hub（模型下载）
- tokenizers（分词器）

> 这些加起来约 1-2GB，是整个安装里最大的部分。CPU 版本就够用，不需要 GPU 版本。

**验证**：输入 `pip list`，能看到上面这些包就成功了。

### 第7步：准备数据目录

**做什么**：
```cmd
if not exist data mkdir data
if not exist documents mkdir documents
```

**解释**：
- 创建 `data/` 文件夹（放数据库和向量索引）
- 创建 `documents/` 文件夹（放 PDF）
- 如果有旧电脑备份，把 `research.db` 放到 `data/`，把 PDF 放到 `documents/`

### 第8步：设置 LLM 环境变量（二选一）

**路线 A：本地 Ollama（V33.9 推荐，8GB 显存）**

先安装 Ollama 并拉取模型，然后：

```cmd
set SCIPAL_LLM_PROVIDER=ollama
set SCIPAL_LLM_HOST=http://localhost:11434
set SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
set SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b
```

**路线 B：OpenAI 兼容云端（DeepSeek / DashScope / OpenAI）**

```cmd
set SCIPAL_LLM_PROVIDER=openai
set SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
set SCIPAL_LLM_API_KEY=你的API_Key
set SCIPAL_LLM_MODEL=deepseek-chat
```

**每个变量的含义**：

| 变量 | 作用 |
|------|------|
| SCIPAL_LLM_PROVIDER | `ollama` 走本地，`openai` 走兼容云端 |
| SCIPAL_LLM_HOST | Ollama 地址（默认 http://localhost:11434） |
| SCIPAL_LLM_MODEL | 重量模型：写综述、问答（本地必须 Q4 量化） |
| SCIPAL_LLM_LIGHT_MODEL | 轻量模型：大纲、证据抽取、引用验证 |
| SCIPAL_LLM_BASE_URL | 云端 API 地址（路线 B） |
| SCIPAL_LLM_API_KEY | 云端身份密钥（路线 B） |

**关于 OFFLINE 模式（可选）**：

```cmd
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
```

- 只有当 embedding（`bge-base-en-v1.5`）和 reranker（`bge-reranker-base`）已在本地缓存、不想联网检查更新时才打开。
- **首次安装/建库请保持关闭**，否则模型下载不下来。
- 这些变量已写进 `start.bat`（默认注释状态），每次启动自动生效，不用手动 `set`。

> 注意：`set` 只在当前 cmd 窗口有效，关窗后失效；所以统一写进 `start.bat` 或 `.env`。

### 第9步：启动服务

**做什么**：
```cmd
python api_server.py
```

**解释**：
- 运行主程序，启动 Flask Web 服务
- 默认监听 `http://127.0.0.1:5000`
- 启动时会加载：
  1. SQLite 数据库（research.db）
  2. Chroma 向量索引（data/chroma/）
  3. embedding 模型（BAAI/bge-base-en-v1.5）
  4. rerank 模型（BAAI/bge-reranker-base）
- 全部加载完后，显示 "Running on http://127.0.0.1:5000"

**为什么必须单线程**：
- PyTorch（深度学习框架）在多线程环境下可能死锁
- 所以 api_server.py 里用了 `threaded=False`
- 这意味着同时只能处理一个请求，但对个人使用完全够了

### 第10步：打开浏览器

**做什么**：浏览器访问 `http://127.0.0.1:5000`

**解释**：
- `127.0.0.1` 就是你自己的电脑（localhost）
- `:5000` 是端口号，Flask 默认用 5000
- 页面加载出来，左侧有论文列表，就成功了

---

## install.bat 逐行解释

```batch
@echo off                                    ← 关闭命令回显（不显示正在执行的命令本身）
chcp 65001 >nul                              ← 设置控制台编码为 UTF-8，支持中文显示
title Sci-Pal 环境安装                        ← 设置窗口标题

python --version >nul 2>&1                   ← 检查 Python 是否安装，输出丢弃
if errorlevel 1 (                            ← 如果上一条命令失败（Python没装）
    echo [错误] 未检测到 Python...           ← 提示用户
    pause                                    ← 暂停，等用户按任意键
    exit /b 1                                ← 退出，返回错误码1
)

if not exist "venv_sciPal\Scripts\activate.bat" (  ← 如果虚拟环境还没创建
    python -m venv venv_sciPal               ← 创建虚拟环境
)

call venv_sciPal\Scripts\activate.bat        ← 激活虚拟环境（call=调用另一个批处理）

python -m pip install --upgrade pip -q       ← 升级 pip（-q=安静模式）
pip install -r requirements.txt              ← 安装所有依赖

echo 安装完成！                               ← 提示
pause                                        ← 暂停，等用户看结果
```

## start.bat 逐行解释

```batch
@echo off
chcp 65001 >nul
title Sci-Pal 科研文献助手

REM ── LLM 配置（默认本地 Ollama，云端用注释切换）──
set SCIPAL_LLM_PROVIDER=ollama              ← ollama=本地 / openai=云端
set SCIPAL_LLM_HOST=http://localhost:11434
set SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
set SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b

REM ── 模型离线模式（可选，默认注释）──
REM set TRANSFORMERS_OFFLINE=1
REM set HF_HUB_OFFLINE=1

if not exist "venv_sciPal\Scripts\activate.bat" (
    echo [提示] 先运行 install.bat            ← 没装环境就提示
    pause
    exit /b 1
)

call venv_sciPal\Scripts\activate.bat        ← 激活虚拟环境

if not exist "data" mkdir data               ← 没有 data 文件夹就创建
if not exist "documents" mkdir documents     ← 没有 documents 就创建

REM 延迟2秒后打开浏览器
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

python api_server.py                         ← 启动服务（这行不会立即返回，一直运行）

pause                                        ← 服务停止后才会到这行
```

---

## 常见问题的底层原因

### Q: 为什么不直接用全局 Python 装包，非要搞虚拟环境？
A: 因为你以后可能装别的 Python 项目，包版本会冲突。虚拟环境是行业标准做法，每个项目独立。

### Q: 什么时候才需要设 TRANSFORMERS_OFFLINE=1？
A: 这是**可选项，不是必须**。当 embedding/reranker 模型已在本地缓存、且不想每次启动联网检查更新时再打开；首次安装或需要下载模型时保持关闭，否则模型拉不下来。

### Q: 为什么 Flask 要用单线程？
A: PyTorch（sentence-transformers 用的深度学习框架）在 Flask 多线程模式下可能死锁。这是 PyTorch + Flask 的已知问题，单线程是标准解法。个人用单线程完全够。

### Q: pip install 很慢怎么办？
A: 用国内镜像源：
```cmd
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```
清华镜像，速度快很多。

### Q: 装到一半报错了怎么办？
A: 看报错信息最后几行，通常是：
- `Microsoft Visual C++ 14.0 is required` → 装 Visual Studio Build Tools
- `Read timed out` → 网络问题，重试或换镜像源
- `No matching distribution` → Python 版本不对，确认是 3.10 或 3.11

---

## 完整的手动安装命令（复制粘贴版）

如果你不想用 install.bat，想自己一步步敲，按顺序执行：

```cmd
:: 第1步：进入项目目录（假设在 D:\sciPal）
D:
cd D:\sciPal

:: 第2步：创建虚拟环境
python -m venv venv_sciPal

:: 第3步：激活
venv_sciPal\Scripts\activate.bat

:: 第4步：升级pip
python -m pip install --upgrade pip

:: 第5步：装依赖（用清华镜像加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

:: 第6步：创建数据目录
if not exist data mkdir data
if not exist documents mkdir documents

:: 第7步：设置 LLM（默认本地 Ollama；云端见下方注释）
set SCIPAL_LLM_PROVIDER=ollama
set SCIPAL_LLM_HOST=http://localhost:11434
set SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
set SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b
:: 云端路线（DeepSeek）：
:: set SCIPAL_LLM_PROVIDER=openai
:: set SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
:: set SCIPAL_LLM_API_KEY=sk-xxxxxx
:: set SCIPAL_LLM_MODEL=deepseek-chat

:: 第8步：启动
python api_server.py
```

然后浏览器打开 http://127.0.0.1:5000
