# SciPal MCP Server（单进程薄转发）

把 SciPal 已有的 Flask API 暴露成 MCP 工具，供 DSH Desktop 调用。

**它不承载任何业务逻辑**：所有工具只做一次 HTTP 转发，不 import SciPal 内部模块。

---

## 1. 为什么是「薄转发」

架构裁决见 [`docs/DSH契约要点.md`](../docs/DSH契约要点.md) §8.2。核心事实：

| 事实 | 后果 |
|---|---|
| embedding / Cross-Encoder reranker / ChromaDB 都是**进程级资源** | 每个 MCP server 都是独立进程 → 拆多个 = 多份模型 |
| 本机 RTX 4060 8 GB | 装不下第二份 |
| Flask 进程本就常驻且已加载全部模型 | 转发零增量成本；新起进程是全量成本 |

### 两条硬性约束（违反即设计失效）

1. **纯 HTTP 客户端**：`scipal_server.py` 禁止 `from services...` / `import app` / `sys.path` 注入。
   一旦 import，模型会被加载进 MCP 子进程，"单进程"立刻作废。
   本目录代码的全部依赖只有 **标准库 + `mcp` SDK**。
2. **不改 Flask 业务代码**：只调现有路由。路由不够用应另开工单，不在 MCP 层绕。

---

## 2. 文件

| 文件 | 作用 |
|---|---|
| `scipal_server.py` | MCP Server 本体（5 个只读工具，stdio） |
| `selftest.py` | 自检：拉起独立 stdio 子进程跑完整协议链路，自适应 Flask 在/不在两种状态 |
| `README.md` | 本文 |

> `tests/mcp_ping_server.py`（阶段零 A）保留不动，它是 MCP 通路验证的存证。

---

## 3. 环境要求

| 项 | 要求 |
|---|---|
| Python | `venv_sciPal_py312`（项目虚拟环境） |
| mcp SDK | **2.2.0**（`FastMCP` 已更名为 `MCPServer`；字段全 snake_case） |
| SciPal API | 需先启动 `python api_server.py`（默认 `http://127.0.0.1:5000`） |

> ⚠️ 系统 PATH 里的 `python` **没有装 mcp SDK**，必须用 venv 的绝对路径
> `D:/sciPal/venv_sciPal_py312/Scripts/python.exe`。用错解释器时
> `failOnStartupError: false` 会让失败**静默**（DSH 工具列表里什么都看不到）。

---

## 4. 运行

### 4.1 由 DSH 拉起（正常用法）

不需要手工运行。DSH 的 `dsh-mcp-client` 会以 stdio 拉起子进程：

```powershell
venv_sciPal_py312\Scripts\python.exe mcp_server\scipal_server.py
```

`stdio` 模式下 **stdout 是 JSON-RPC 通道**，本 Server 绝不向 stdout 打印任何内容
（日志走 stderr）。

### 4.2 自检

```powershell
cd d:\sciPal
.\venv_sciPal_py312\Scripts\python.exe mcp_server\selftest.py
```

退出码 `0` = PASS，`1` = FAIL。

自检做三件事（自适应 Flask 状态）：

1. `tools/list` 必须**恰好**返回 5 个工具：`health` / `search_papers` / `get_paper` / `get_abstract` / `task_status`
2. **Flask 在跑** → `tools/call(health)` 必须 `is_error=False`，且 `data.status == "ok"`
3. **Flask 未跑** → `tools/call(health)` 必须 `is_error=True`，且文本含「SciPal API 未启动」

实测输出见第 7 节。

---

## 5. 工具清单

| MCP 工具 | 对应路由 | 入参 | 说明 |
|---|---|---|---|
| `health` | `GET /api/health` | 无 | 存活探测，返回 `status/service/version/db_exists` |
| `search_papers` | `POST /api/search/hybrid` | `query` (str, 必填)<br>`top_k` (int, 默认 **10**)<br>`use_online` (bool, 默认 **False**) | **MCP 侧 `use_online` 默认关闭**（见下） |
| `get_paper` | `GET /api/papers/<paper_id>` | `paper_id` (str, 必填) | 元数据 + 引用/被引/相似 |
| `get_abstract` | `GET /api/abstracts/<paper_id>` | `paper_id` (str, 必填) | ⚠️ 该路由实际按 **PMID** 查询，传 PMID |
| `task_status` | `GET /api/tasks/<task_id>` | `task_id` (str, 必填) | 长任务轮询入口 |

### 5.1 两个必须知道的参数映射

**① `query` → Flask 的 `q`**

`api_server.py` 的 `/api/search/hybrid` 读的是 **`q`**，不是 `query`：

```python
query = data.get("q", "").strip()      # api_server.py:1041
```

MCP 工具对外暴露 `query`（对模型更自然），转发时映射为 `q`。直接传 `query` 给 Flask 会返回 400「缺少搜索关键词 q」。

**② `get_abstract` 的参数语义是 PMID**

```python
row = conn.execute("SELECT ... FROM papers WHERE pmid = ?", (paper_id,))   # api_server.py:1596
```

工具参数名沿用 `paper_id`，但实际要传 **PMID**（abstracts.db 的主键）。

### 5.2 `use_online` 为什么默认 False

`/api/search/hybrid` 服务端默认 `use_online=True`（`api_server.py:1043`），会去打 NCBI PubMed/PMC，
很容易超过 MCP 的 `toolCallTimeoutMs`（60 秒）。因此 MCP 工具侧默认关闭在线检索，
需要时由模型显式传 `True`。

---

## 6. 配进 DSH

在 `C:\Users\chenwei\.dsh\profiles\desktop\cordis.patch.yml` 的顶层数组**追加**（不要覆盖已有 `- id: locale`）：

```yaml
- id: mcp-scipal
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: scipal
    transport: stdio
    command: 'D:/sciPal/venv_sciPal_py312/Scripts/python.exe'
    args: ['D:/sciPal/mcp_server/scipal_server.py']
    cwd: 'D:/sciPal'
    env:
      # base_url 一般不用改；如需指向别的端口再覆盖
      SCIPAL_BASE_URL: 'http://127.0.0.1:5000'
      PYTHONUTF8: '1'
    toolCallTimeoutMs: 60000
    failOnStartupError: false
```

工具公开名为 `mcp__scipal__<tool>`，例如 `mcp__scipal__health`。

**环境清洗提醒**：stdio 子进程会删除所有匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的环境变量以及 `DSH_*`。
`SCIPAL_BASE_URL` / `PYTHONUTF8` 不含上述模式，可安全声明；若后续要传
`SCIPAL_PROTOCOLS_IO_TOKEN`、`NCBI_API_KEY` 之类，必须在 `env:` 里**显式写值**。

---

## 7. 实测记录（2026-10-24）

### 7.1 `tools/list`

```text
[selftest] tools.count  : 5
[selftest] tools        : ['get_abstract', 'get_paper', 'health', 'search_papers', 'task_status']
```

### 7.2 Flask 在跑

```text
[selftest] flask        : RUNNING (http://127.0.0.1:5000)
[selftest] health.error : False
[selftest] health.text  : { |   "ok": true, |   "status": 200, |   "data": { |
    "db_exists": true, |     "service": "sci-pal", |     "status": "ok", |
    "version": "V25.14" |   } | }
[selftest] RESULT       : PASS
```

补充验证（同一进程内调用）：

```text
[probe] search_papers   is_error=False {'ok': True, 'status': 200, 'total': 3, 'local_count': 3, 'online_count': 0}
[probe] get_paper       is_error=False {'ok': False, 'status': 404}
```

- `search_papers` 的 `query → q` 映射生效；`use_online` 默认 False 生效（`online_count=0`）
- 4xx 按「业务结果」返回 `{"ok": false, "status": 404}`，`is_error=False`

### 7.3 Flask 未跑

```text
[selftest] flask        : NOT RUNNING (http://127.0.0.1:5000)
[selftest] health.error : True
[selftest] health.text  : Error executing tool health: SciPal API 未启动：连接
    http://127.0.0.1:5000 失败，请先运行 python api_server.py（详情：[WinError 10061]
    No connection could be made because the target machine actively refused it）
[selftest] RESULT       : PASS
```

---

## 8. 已知限制（如实记录，未在本工单修复）

### 8.1 `task_status` 在当前数据库上返回 500

实测 `GET /api/tasks/<任意 id>` → **500**，Flask 侧 traceback：

```text
File "d:\sciPal\services\unified_task_manager.py", line 103, in get_task
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
sqlite3.OperationalError: no such table: tasks
```

核对结果：

| 检查 | 实测 |
|---|---|
| `data/research.db` 表数量 | 32 |
| 是否存在 `tasks` 表 | ❌ **不存在** |
| `api_server.py:1958 run_db_migrations()` 职责 | 只给 `papers` 补 `volume/issue/pages` 字段，**不建 tasks 表** |
| `database/init_db.py:299` | 有 `CREATE TABLE tasks`，但该脚本是旧 schema，当前库来源是 `build_db/` |

→ 这是 **Flask / 数据库侧既有缺陷**，不是转发层问题：MCP 侧已把 5xx 正确转为
`is_error=True` 的受控错误，没有崩溃也没有静默。按工单「不许改 Flask 业务代码」，
本工单只报告，需另开工单建表。

### 8.2 其他

| 限制 | 说明 |
|---|---|
| 单次 HTTP 超时 45 s | 留 15 s 余量给 MCP 的 60 s 上限；更长的任务必须走 job 句柄 + `task_status` 轮询 |
| `use_online=True` 可能超时 | 在线检索走 NCBI，网络慢时仍可能触及 45 s |
| 长任务无同步等待 | DSH 不支持 task-based execution，本设计一律「立即返回句柄 + 轮询」 |
| `search_papers` 结果体量 | 默认 `top_k=10`；大结果会占用较多上下文，按需调小 |
