# Windows 开发警示与跨平台规范

> 适用：SciPal 所有开发、脚本、评测、部署代码  
> 生产目标：Linux 服务器 / 超算集群  
> Windows 定位：**仅开发机，不是生产环境**

---

## 0. 一句话原则

```text
Windows 上写代码，必须假设它明天就会在 Linux 上跑。
```

不要写“先在 Windows 上能跑，Linux 以后再说”的代码。  
SciPal 的部署目标不是 Windows；Windows 只是开发工具。

---

## 1. 硬性规则

### 规则 1：禁止盘符绝对路径

禁止：

```python
D:\models\models\BAAI--bge-base-en-v1.5
C:\data\research.db
G:\runs\scifact_data
```

正确：

```python
from config.paths import MODELS_DIR, DB_PATH

model_dir = MODELS_DIR / "bge-base-en-v1.5"
db_path = DB_PATH
```

需要用户自定义：

```text
SCIPAL_DATA_DIR
SCIPAL_MODELS_DIR
SCIPAL_DB_PATH
SCIPAL_EMBEDDING_MODEL
SCIPAL_RERANK_MODEL
```

### 规则 2：禁止假设当前工作目录

禁止：

```python
open("data/research.db")
Path("logs/stop_loss_state.json")
os.getcwd() / "csl_styles"
```

正确：

```python
from config.paths import DB_PATH, LOGS_DIR, PROJECT_ROOT

conn = sqlite3.connect(DB_PATH)
state = LOGS_DIR / "stop_loss_state.json"
styles = PROJECT_ROOT / "csl_styles"
```

原因：

```text
Windows 计划任务、systemd、cron、容器的工作目录都不同。
cwd 不是项目根。
```

### 规则 3：禁止字符串拼接路径

禁止：

```python
path = base + "/" + filename
path = f"{dir}/{file}"
path = dir + "\\" + file
```

正确：

```python
path = base / filename
path = Path(base) / filename
path = os.path.join(base, filename)   # 旧代码允许，但新代码优先 pathlib
```

注意：

```text
HTTP URL 的 "/" 拼接不属于文件路径，可以保留。
```

### 规则 4：临时文件只用 tempfile

禁止：

```python
tmp = "/tmp/scipal"
tmp = "C:\\Temp\\scipal"
tmp = os.environ["TEMP"] + "/scipal"
```

正确：

```python
import tempfile

with tempfile.TemporaryDirectory(prefix="scipal_") as tmp:
    out = Path(tmp) / "out"
```

需要原子替换时：

```python
handle, tmp_name = tempfile.mkstemp(dir=target.parent)
```

说明：

```text
MinerU 的临时目录已经使用 tempfile。
Docling / GROBID 当前不落临时文件。
不要为了“看得见”把临时目录改到项目根。
```

### 规则 5：禁止写死解释器和虚拟环境路径

禁止：

```python
"venv_sciPal_py312/Scripts/python.exe"
"venv/bin/python"
"/usr/bin/python3"
```

正确：

```python
import sys
from pathlib import Path

python = Path(sys.executable).resolve()
```

启动子进程：

```python
subprocess.run([str(python), str(script), ...], cwd=str(PROJECT_ROOT))
```

### 规则 6：路径必须来自 config.paths 或环境变量

项目内路径统一入口：

```text
config/paths.py
```

当前提供：

```text
PROJECT_ROOT
DATA_DIR
DOCUMENTS_DIR
XML_DIR
LOGS_DIR
MODELS_DIR
DB_PATH
CHROMA_PATH
EMBEDDING_MODEL
RERANK_MODEL
```

新增路径时：

```text
先加到 config/paths.py
不要在业务模块里再造一个 PROJECT_ROOT
```

### 规则 7：提交前必须在非项目目录跑一次

```powershell
cd $env:TEMP
python D:\path\to\sciPal\scripts\your_script.py --help
```

如果只在项目根能跑，说明还有 cwd 依赖。

---

## 2. Windows 特有的坑

| 坑 | 表现 | 规则 |
|---|---|---|
| 盘符路径 | Linux 上不存在 | 用 config.paths |
| 反斜杠 | Linux 当普通字符 | 用 `/` 或 pathlib |
| 大小写不敏感 | Windows 能跑，Linux 找不到文件 | 导入/文件名严格大小写 |
| CRLF | shell 脚本报 `\r` | `.gitattributes` / 编辑器设 LF |
| 文件锁 | Windows 不能删被占用文件 | 用 tempfile/上下文管理器 |
| 多进程 spawn | Windows 重跑 `__main__` | 子进程入口加 `if __name__ == "__main__"` |
| 信号 | `SIGTERM` 行为不同 | 不依赖 Unix 信号做核心逻辑 |
| 权限 | `chmod` 无效 | 不靠权限位做安全边界 |
| 符号链接 | 需要管理员/开发者模式 | 测试不要依赖 symlink |
| 长路径 | 260 字符限制 | 少用超长嵌套目录 |
| 端口占用 | Windows 复用行为不同 | 测试用随机端口 |
| 换行/编码 | GBK 控制台 | 统一 UTF-8，`PYTHONUTF8=1` |

---

## 3. 模型与离线部署

默认模型是 HuggingFace ID：

```text
BAAI/bge-base-en-v1.5
BAAI/bge-reranker-base
```

Linux 离线/超算必须显式指定本地目录：

```bash
export SCIPAL_EMBEDDING_MODEL=/data/models/BAAI--bge-base-en-v1.5
export SCIPAL_RERANK_MODEL=/data/models/BAAI--bge-reranker-base
```

Docker Compose 已经设置：

```yaml
SCIPAL_EMBEDDING_MODEL: /models/models/BAAI--bge-base-en-v1.5
SCIPAL_RERANK_MODEL: /models/models/BAAI--bge-reranker-base
```

不要假设模型在：

```text
D:\models
/root/.cache
项目根/models
```

除非环境变量明确指向。

---

## 4. 提交前检查清单

每个 PR 必须确认：

```text
[ ] 没有 D:\ / C:\ / G:\ 等盘符路径
[ ] 没有 /home/xxx、/data/models 等固定 Linux 路径
[ ] 没有 os.getcwd() 拼路径
[ ] 没有 Path("data") / Path("logs") 这类 cwd 相对路径
[ ] 文件路径用 pathlib 或 os.path.join
[ ] 临时文件用 tempfile
[ ] 子进程解释器用 sys.executable
[ ] 非项目目录下 --help / 最小命令能跑
[ ] 719+ 测试通过
[ ] 新增路径已加入 config/paths.py
```

自动检查：

```powershell
python scripts/check_portability.py
python -m unittest tests.test_paths -v
```

CI 建议：

```yaml
- run: python scripts/check_portability.py
- run: python -m unittest tests.test_paths -v
```

---

## 5. 代码评审时的问法

看到路径代码，先问：

```text
1. 这个路径从哪来？
2. 换一台 Linux 机器还在吗？
3. 从 systemd / cron / 容器启动还在吗？
4. 用户能通过环境变量覆盖吗？
5. 临时文件退出后会清理吗？
```

如果答不上来，不要合并。

---

## 6. Linux 机器坏了怎么办

明确原则：

```text
Windows 不是备选生产环境。
```

Linux 主机不可用时：

```text
优先：修 Linux / 换 Linux 主机 / 用容器或 WSL2 做临时验证
禁止：把 Windows 当生产部署，改路径“先跑起来”
```

原因：

```text
一旦为了 Windows 生产改路径，
就会重新引入盘符、cwd、反斜杠、文件锁、编码问题，
下一次 Linux 部署会再次踩坑。
```

Windows 只做：

```text
开发、IDE、单测、离线文档、前端预览
```

---

## 7. 相关文档

```text
docs/跨平台路径体检报告.md      本次体检结果与修改清单
config/paths.py                 唯一路径入口
tests/test_paths.py             路径回归测试
scripts/check_portability.py    提交前自动扫描
```

---

## 8. 最后一句

```text
路径问题不是“环境问题”，是代码问题。
能在 Windows 跑，不等于能在 Linux 跑；
能在项目根跑，不等于能在 systemd 跑。
```

把这条贴在开发机旁边。
