# Sci-Pal Windows 环境重建指南

> 本文档适用于在 Windows 10/11 上从零重建 Sci-Pal 科研文献助手环境。

---

## 一、系统要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| 操作系统 | Windows 10 64位 | Windows 11 |
| Python | 3.10 | 3.11（最稳） |
| 内存 | 8GB | 16GB+ |
| 磁盘空间 | 5GB（代码+模型） | 20GB+（含PDF和数据库） |
| GPU | 不需要 | 有更好（embedding更快） |

**不需要**：Docker、GROBID、CUDA、Git、Ollama（用DeepSeek在线API的话）

---

## 二、安装步骤（约15-30分钟）

### 第1步：安装 Python

1. 去 https://www.python.org/downloads/ 下载 **Python 3.11**（不要用3.12+，有些包还没适配）
2. 安装时**务必勾选 "Add Python to PATH"**
3. 安装完成后，打开 cmd，输入 `python --version`，显示版本号即成功

### 第2步：解压代码包

把 `Sci-Pal-V26.2-WINDOWS.zip` 解压到比如 `D:\sciPal\`，路径里**不要有中文和空格**。

### 第3步：一键安装环境

双击 `install.bat`，脚本会自动：
- 创建虚拟环境 `venv_sciPal`
- 升级 pip
- 安装 `requirements.txt` 里的所有依赖

首次安装约 5-15 分钟（取决于网速），看到"安装完成"即成功。

> **如果 docling 安装报错**：需要先装 Visual Studio Build Tools
> 下载：https://visualstudio.microsoft.com/visual-cpp-build-tools/
> 安装时勾选 "Desktop development with C++"，装完重启再运行 install.bat

### 第4步：恢复数据（如果有旧电脑备份）

把旧电脑的以下文件/文件夹拷到对应位置：

| 旧电脑路径 | 拷到 Windows 路径 | 重要性 |
|-----------|------------------|--------|
| `data/research.db` | `D:\sciPal\data\research.db` | ⭐⭐⭐ 必须 |
| `data/chroma/`（整个文件夹） | `D:\sciPal\data\chroma\` | ⭐⭐⭐ 必须 |
| `documents/`（所有PDF） | `D:\sciPal\documents\` | ⭐⭐ 建议 |
| `data/outlines/` | `D:\sciPal\data\outlines\` | ⭐ 可选 |
| `.env` | `D:\sciPal\.env` | ⭐ 可选 |

> 如果旧电脑读不出来，没有备份，请看第五节"从零开始建库"。

### 第5步：配置 DeepSeek API

用记事本打开 `start.bat`，找到这一行：
```
set SCIPAL_LLM_API_KEY=在这里填你的DeepSeek_API_Key
```
把 `在这里填你的DeepSeek_API_Key` 改成你的真实 API Key，保存。

> API Key 申请：https://platform.deepseek.com/ ，注册后在"API Keys"里创建

### 第6步：启动

双击 `start.bat`，浏览器会自动打开 `http://127.0.0.1:5000`。

看到页面加载出来，左侧有论文列表，就说明成功了。

---

## 三、日常使用

| 操作 | 方法 |
|------|------|
| 启动服务 | 双击 `start.bat` |
| 停止服务 | 在 cmd 窗口按 `Ctrl+C`，或直接关窗口 |
| 重新安装依赖 | 双击 `install.bat` |
| 运行自检 | cmd 里执行 `venv_sciPal\Scripts\activate` 然后 `python scripts\self_check.py` |

---

## 四、常见问题

### Q1: 启动时报 "No module named xxx"
A: 依赖没装全，重新双击 `install.bat`。

### Q2: 启动时报 "Connection failed" 或模型加载失败
A: 检查 `data/chroma/` 文件夹是否存在，模型文件是否完整。如果模型文件丢失，删掉 `data/chroma/`，运行 `python -m build_db.build_embeddings` 重建（需要联网下载模型，约1.5GB）。

### Q3: DeepSeek 问答报 400 错误
A: 检查 `start.bat` 里的模型名是不是 `deepseek-chat`，API Key 是不是正确。不要用 `qwen-plus` 等其他模型名。

### Q4: 浏览器打开是空白
A: 刷新一下页面，或者检查 cmd 窗口有没有报错。确认 `frontend/` 文件夹存在。

### Q5: PowerShell 里运行脚本报"禁止运行脚本"
A: 用 **cmd** 而不是 PowerShell，或者在 PowerShell 里执行一次：
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
选 Y 确认。

### Q6: 虚拟环境激活后命令行前面没有 (venv_sciPal)
A: 正常现象，Windows 上有时候不显示，但环境已经激活了。输入 `where python` 看路径是不是在 `venv_sciPal\Scripts\` 下。

---

## 五、从零开始建库（没有旧数据备份时）

如果旧电脑数据彻底丢了，按以下步骤重建：

### 5.1 准备 PDF
把所有论文 PDF 放到 `documents/` 文件夹。

### 5.2 建库
```cmd
venv_sciPal\Scripts\activate
set TRANSFORMERS_OFFLINE=0
set HF_HUB_OFFLINE=0
python -m build_db.build_database
```
> 首次运行会自动下载 embedding 模型（all-mpnet-base-v2，约420MB）和 rerank 模型（bge-reranker-base，约1GB）

### 5.3 建向量索引
```cmd
python -m build_db.build_embeddings
```

### 5.4 建全文检索索引
```cmd
python -m build_db.build_fts
```

### 5.5 建知识图谱
```cmd
python -m build_db.build_paper_graph --apply
```

### 5.6 运行自检
```cmd
python scripts\self_check.py
```
全部通过（除了大纲存储的2个已知失败项）就可以用了。

---

## 六、目录结构说明

```
D:\sciPal\
├── api_server.py          # 主程序入口
├── start.bat              # Windows 一键启动
├── install.bat            # Windows 一键安装环境
├── requirements.txt       # 依赖清单
├── README-WINDOWS.md      # 本文档
├── ARCHITECTURE.md        # 架构说明
├── WORKLOG.md             # 开发日志
├── VERSION                # 版本号
├── venv_sciPal\           # 虚拟环境（install.bat自动创建）
├── data\
│   ├── research.db        # SQLite 数据库（论文/段落/图表/图谱）
│   ├── chroma\            # 向量索引
│   └── outlines\          # 大纲存储
├── documents\             # PDF 源文件
├── frontend\              # 前端页面（HTML/CSS/JS）
├── services\              # 后端服务（检索/问答/LLM/PDF）
├── build_db\              # 建库脚本
├── scripts\               # 工具脚本（自检/调参/去重）
├── config\                # 配置文件
└── tests\                 # 测试
```

---

## 七、联系与反馈

如果遇到本文档没覆盖的问题，检查：
1. cmd 窗口的报错信息
2. `scripts\self_check.py` 的自检结果
3. 浏览器 F12 控制台的报错

把报错信息截图，就能快速定位问题。
