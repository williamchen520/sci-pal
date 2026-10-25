# SciPal MCP Server（薄转发，按业务流拆三个服务）

把 SciPal 已有的 Flask API 暴露成 MCP 工具，供 DSH Desktop 调用。

**它不承载任何业务逻辑**：所有工具只做一次 HTTP 转发，不 import SciPal 内部模块。

当前挂载 **3 个 stdio 服务 / 共 20 个工具**：
`scipalhello`（哨兵 1）+ `scipal-search`（10）+ `scipal-generate`（9）。

---

## 1. 为什么是「薄转发」

架构裁决见 [`docs/DSH契约要点.md`](../docs/DSH契约要点.md) §8.2。

**为什么拆成多进程而不是一个**（2026-10-24 实测更正）：

| 事实 | 后果 |
|---|---|
| embedding / reranker / ChromaDB 全在 **Flask 进程**里，MCP 侧只是 HTTP 客户端 | MCP 子进程**不加载模型**，单个 server 实测常驻 ≈ **68 MB** |
| 显存不是约束（模型仍在 5000 端口那一个 Flask 里） | 拆 server **不复制模型**，VRAM 不变 |
| 真正的约束是**模型上下文与工具数** | 单 server 工具过多会挤占上下文、降低选择准确率 → 按业务流拆，每 server 以 8 个为基准（现有 10 / 9 / 1 均属同一工作流闭环的破例，理由见 `docs/DSH插件化-路线图.md` §2.3） |

> 早期文档写「拆多个 = 多份模型、8 GB 装不下」是**错的**：那条推论的错误前提是
> MCP 进程会 import 业务模块。只要守住下面的约束 1，就不会发生。

### 三条硬性约束（违反即设计失效）

1. **纯 HTTP 客户端**：任何 `*_server.py` 禁止 `from services...` / `import api_server` /
   向 `sys.path` 注入项目根。一旦 import，模型会被加载进 MCP 子进程，轻薄转发立刻作废。
   本目录代码的全部依赖只有 **标准库 + `mcp` SDK**。
   （唯一的 `sys.path.insert` 允许把 `mcp_server/` 自己插进去，用于 `import _forward`。）
2. **不改 Flask 业务代码**：只调现有路由。路由不够用应另开工单，不在 MCP 层绕。
3. **绝不向 stdout 打印**：stdio 模式下 stdout 是 JSON-RPC 通道，一行 `print()` 就会破坏协议。

---

## 2. 文件

| 文件 | 作用 |
|---|---|
| `_forward.py` | 公共薄转发层：HTTP 请求 + 错误映射，**零业务逻辑** |
| `search_server.py` | 检索类 server `scipal-search`（6 工具） |
| `generate_server.py` | 生成/查询类 server `scipal-generate`（9 工具） |
| `scipal_server.py` | **旧单进程 server（5 工具），已从 bundle 摘除，保留作回退**，不要重新挂载 |
| `selftest.py` | 自检：拉起 3 个独立 stdio 子进程跑完整协议链路，逐工具 PASS/FAIL |
| `README.md` | 本文 |

> `tests/mcp_ping_server.py`（阶段零 A）保留不动，它是哨兵 `scipalhello` 的实现，
> 零依赖、不碰 Flask，用来区分「DSH 侧配置问题」和「SciPal 侧服务问题」。

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

不需要手工运行。DSH 的 `dsh-mcp-client` 会为每个 serverName 各起一个 stdio 子进程：

```powershell
venv_sciPal_py312\Scripts\python.exe mcp_server\search_server.py     # scipal-search
venv_sciPal_py312\Scripts\python.exe mcp_server\generate_server.py   # scipal-generate
venv_sciPal_py312\Scripts\python.exe tests\mcp_ping_server.py        # scipalhello（哨兵）
```

`stdio` 模式下 **stdout 是 JSON-RPC 通道**，三个 Server 都不向 stdout 打印任何内容（日志走 stderr）。

> 进程计数别数错：本机每条命令会出**两层** `python.exe`（venv 启动器 + 它 fork 的系统 python）。
> 3 条命令 = **6 个** python 进程，其中含 `mcp_server/` 或 `mcp_ping_server` 的那 6 个才是 MCP。

### 4.2 自检

```powershell
cd d:\sciPal
.\venv_sciPal_py312\Scripts\python.exe mcp_server\selftest.py
```

退出码 `0` = PASS，`1` = FAIL。自检**真实拉起 3 个 stdio 子进程并真实调 HTTP**，
共 **22 条断言**，逐工具打 PASS/FAIL：

| server | 工具数 | 断言数 | 说明 |
|---|---|---|---|
| `scipal`（legacy 回退入口） | 5 | 6 | `tools/list` 1 + 5 次调用 |
| `scipal-search` | 10 | 11 | `tools/list` 1 + 10 次调用 |
| `scipal-generate` | 9 | 10 | `tools/list` 1 + 9 次调用 |
| **合计** | **24** | **27** | 哨兵由 `tests/mcp_ping_server.py --selftest` 单独验证 |

特殊断言（阶段六-B 起，共 5 个异步 submit：`generate_outline` / `generate_review` /
`ask_question` / `agentic_search` / `parse_paper`）：

- `generate_outline`：**必须 <10 s 返回且含 `task_id`**（这是「异步」的判据，不是看 `is_error`）
- `cancel_review_task`：用不存在的 id，**期望 `status=404`**（业务错误算通过）
- `generate_outline` 放在 `scipal-generate` 的最后一条跑 —— 它起的大纲任务会把单线程 Flask 饿住，
  放在最后不拖累其它断言

> **业务性 400/404 不算失败**：它证明链路通、参数名对，只是数据不存在。
> 只有 `unknown tool` / 连不上才算失败。

---

## 5. 工具清单（20 个）

### 5.1 `scipal-search`（10）

| MCP 工具 | 对应路由 | 入参 |
|---|---|---|
| `health` | `GET /api/health` | 无 |
| `search_hybrid` | `POST /api/search/hybrid` | `query`(必填) / `top_k`=10 / `use_online`=False |
| `search_online` | `POST /api/search/online` | `query`(必填) / `max_results`=20 / `search_pubmed`=True / `search_pmc`=True |
| `get_paper` | `GET /api/papers/<id>` | `paper_id`(必填) |
| `download_online_papers` | `POST /api/search/download_online` | `pmc_ids`(必填) → **立即返 `task_id`** |
| `download_status` | `GET /api/search/download_status` | `task_id`(必填) |
| `ask_question` | `POST /api/qa/ask_async` | `question`(必填) / `paper_id`="" / `diagnostics`=False → **立即返 `task_id`**（单次 >120 s，必须轮询） |
| `agentic_search` | `POST /api/agentic/search_async` | `query`(必填) / `max_hops`=3(钳 1-5) / `min_coverage`=0.6 / `top_paragraphs`=6 / `paper_id`="" → **立即返 `task_id`** |
| `list_local_papers` | `GET /api/papers/local` | `only_unparsed`=False / `limit`=20（裁剪为 6 个精简字段，防上下文爆炸；超出标「已截断」） |
| `parse_paper` | `POST /api/papers/parse_async` | `filename`(必填) → **立即返 `task_id`**；只能解析 `documents/` 已有 PDF，**不能上传** |

### 5.2 `scipal-generate`（9）

| MCP 工具 | 对应路由 | 入参 |
|---|---|---|
| `health` | `GET /api/health` | 无 |
| `list_saved_outlines` | `GET /api/review/outline/saved` | 无 |
| `get_saved_outline` | `GET /api/review/outline/saved/<name>` | `name`(必填) |
| `get_review` | `GET /api/review/<id>` | `review_id`(必填) |
| `paper_citation_graph` | `GET /api/papers/<id>/graph` | `paper_id`(必填) / `relation`=all / `direction`=both / `max_hops`=1(钳 1-3) / `max_total`=10 |
| `review_task_status` | `GET /api/review/task/<id>` | `task_id`(必填) |
| `generate_outline` | `POST /api/review/outline` | `topic`(必填) / `max_papers`=20 / `review_type`=narrative / `language`=en → **立即返 `task_id`** |
| `cancel_review_task` | `POST /api/review/cancel/<id>` | `task_id`(必填)；不存在/已结束 → 404 |
| `generate_review` | `POST /api/review/generate_async` | `topic`(必填) / `max_papers`=20 / `use_llm_verify`=False / `citation_style`=apa / `review_type`=narrative / `language`=en → **立即返 `task_id`**（不支持 `custom_outline`） |

> ⚠️ **能力边界（阶段五-C C-2 更新）**：
>
> - ✅ `generate_outline` **可提交**：`POST /api/review/outline` 自 V26.3 起就是**异步**的 —
>   服务端建任务后**立即返回 `task_id`**（实测 **~0.13 s**）。
> - ✅ `generate_review` **可提交**（C-2 新增）：`POST /api/review/generate_async`，
>   实测 **0.050 / 0.346 s** 返回 `task_id`；整条流水线分钟级。
>   **不支持 `custom_outline`**（嵌套 JSON，MCP 参数只吃标量）。
> - ❌ 仍不挂：`/api/agentic/search`、`/api/qa/ask`、`/api/papers/parse`（同步）、
>   `/api/papers/import`（multipart）。
>
> **轮询节奏**：C-2 已把 Flask 改为 `threaded=True`，任务运行期间 `/api/health` 实测
> **0.058–0.132 s**（并发两个综述任务时 10 次采样）。但**冷加载**（embedding/reranker 首次
> 装载，约 +1.5 GB）仍会把解释器饿到 **20 s 以上** —— 那是**一次性**的，与 async 无关，
> 先随便调一次熬过去即可。轮询间隔仍建议 **≥5 s**。
>
> **取消语义**：只在**阶段之间**生效（检索 / 证据抽取 / 大纲 / 撰写 / 校验，共 5 个点）；
> **正在撰写正文时不可中断**，取消要等这段 LLM 调用跑完，才会在「校验前」被观察到。
>
> 📌 **`≤8 工具` 上限第 2 次破例**：`scipal-generate` 现在 9 个工具。两个 submit 类工具
> （`generate_outline` / `generate_review`）与同 server 的结果读取（`get_review` /
> `get_saved_outline` / `review_task_status`）是同一工作流闭环；拆第 4 个 server 要多 1 个
> 常驻进程（≈68 MB）换不来收益，还多一层配置与故障面。（第 1 次破例是 C-1 的 `generate_outline`。）

### 5.3 `scipalhello`（1）

| MCP 工具 | 实现 | 用途 |
|---|---|---|
| `ping` | `tests/mcp_ping_server.py` | 零依赖哨兵。它活着 = DSH 侧配置正确；它挂了 = DSH/配置层问题 |

### 5.4 两个必须知道的参数映射

**① `query` → Flask 的 `q`**

`api_server.py` 的 `/api/search/hybrid` 读的是 **`q`**，不是 `query`：

```python
query = data.get("q", "").strip()      # api_server.py:1041
```

MCP 工具对外暴露 `query`（对模型更自然），转发时映射为 `q`。直接传 `query` 给 Flask 会返回 400「缺少搜索关键词 q」。

**② `get_paper` 的 `paper_id` 不是 PMID**

旧 `get_abstract` 工具（已随 legacy server 摘除）按 **PMID** 查 `papers.pmid`；
而 `get_paper` 按 **paper_id** 查主键。两者语义不同，别混用。

### 5.5 `use_online` 为什么默认 False

`/api/search/hybrid` 服务端默认 `use_online=True`（`api_server.py:1043`），会去打 NCBI PubMed/PMC，
很容易超过 MCP 的 `toolCallTimeoutMs`（60 秒）。因此 MCP 工具侧默认关闭在线检索，
需要时由模型显式传 `True`；纯在线检索请改用 `search_online`。

---

## 6. 配进 DSH

**唯一权威来源是 bundle：`packages/dsh-scipal/cordis.patch.yml`**（`insert:` 块内 3 条）。
不要手改 `~/.dsh/profiles/desktop/cordis.patch.yml`，也不要用安装界面的「添加插件」逐个加 MCP ——
装 bundle 就会把这 3 条叠加进去，手写会 serverName 重名、加载直接报错。

写法要点（三条，踩过坑）：

```yaml
- insert:
    - id: mcp-scipal-search                 # 🔴 必须包在 insert: 里
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: scipal-search           # 限 ^[A-Za-z0-9_-]{1,32}$
        transport: stdio
        command: 'D:/sciPal/venv_sciPal_py312/Scripts/python.exe'   # 🔴 必须 venv，系统 python 没 mcp SDK
        args: ['D:/sciPal/mcp_server/search_server.py']
        cwd: 'D:/sciPal'
        env:
          SCIPAL_BASE_URL: 'http://127.0.0.1:5000'
          PYTHONUTF8: '1'
          no_proxy: '127.0.0.1,localhost'   # 🔴 必写，否则本机代理会拦 127.0.0.1
          NO_PROXY: '127.0.0.1,localhost'
        toolCallTimeoutMs: 60000
        failOnStartupError: false           # 业务 server 用 false；哨兵用 true
```

1. **必须包在 `- insert:` 内**。写成顶层 `- id: xxx` 会被当成「覆盖已有行」，
   而该行不存在 → `[warn] patch: entry "xxx" not found` 后**静默跳过**，不报错。
2. **`command` 必须是 venv 的 python**：系统 PATH 的 python 没装 mcp SDK，
   配合 `failOnStartupError: false` 会**静默失败**（工具列表里什么都没有）。
3. **`env` 必须写 `no_proxy` / `NO_PROXY`**：本机 `http_proxy` 会拦 `127.0.0.1:5000`。

工具公开名为 `mcp__<serverName>__<rawName>`，例如：

```text
mcp__scipalhello__ping
mcp__scipal-search__health / search_hybrid / search_online / get_paper /
                      download_online_papers / download_status
mcp__scipal-generate__health / list_saved_outlines / get_saved_outline /
                      get_review / paper_citation_graph / review_task_status
```

**环境清洗提醒**：stdio 子进程会删除所有匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的环境变量以及 `DSH_*`。
`SCIPAL_BASE_URL` / `PYTHONUTF8` 不含上述模式，可安全声明；若后续要传
`SCIPAL_PROTOCOLS_IO_TOKEN`、`NCBI_API_KEY` 之类，必须在 `env:` 里**显式写值**。

---

## 7. 实测记录

### 7.0 三服务自检（2026-10-24 20:47，阶段五-B 验收）

```text
SciPal MCP selftest —— 3 个 server，逐工具真实调用
Flask 基址: http://127.0.0.1:5000

[server] scipal (legacy, 回退入口)  (scipal_server.py)
  [PASS] tools/list  5 个，与期望一致
  [PASS] get_abstract 404 / get_paper 404 / health 200 / search_papers 200 / task_status 404
[server] scipal-search  (search_server.py)
  [PASS] tools/list  6 个，与期望一致
  [PASS] download_online_papers 400 / download_status 404 / get_paper 404
  [PASS] health 200 / search_hybrid 200 / search_online 200
[server] scipal-generate  (generate_server.py)
  [PASS] tools/list  6 个，与期望一致
  [PASS] get_review 404 / get_saved_outline 404 / list_saved_outlines 200
  [PASS] paper_citation_graph 200 / review_task_status 404 / health 200

server 数 : 3    断言总数 : 20    PASS : 20    FAIL : 0    RESULT : PASS
```

> legacy `scipal` 仍被 selftest 覆盖（作回退验证），但**不挂进 bundle**，
> 所以线上工具数是 **15**，而 selftest 覆盖的工具数是 **19**（22 条断言）。

### 7.0.1 阶段五-C C-1（异步大纲接入，2026-10-24 21:33 实测）

`selftest.py`：**3 server / 22 断言 / 全 PASS / exit 0**，`scipal-generate` 期望 **8** 个工具。

```text
[server] scipal-generate  (generate_server.py)
  [PASS] tools/list  8 个，与期望一致
  [PASS] health / list_saved_outlines / get_saved_outline / get_review /
         paper_citation_graph / review_task_status
  [PASS] cancel_review_task       status=404（期望 404，业务错误算通过）
  [PASS] generate_outline         耗时=0.03s task_id=d0df378f-846e-4bc1-88e7-456eec91e422（要求 <10s 且非空）

server 数 : 3    断言总数 : 22    PASS : 22    FAIL : 0    RESULT : PASS
```

`generate_outline` 经 MCP 转发的完整返回（实测 **0.036 s**，异步判据成立）：

```json
{
  "ok": true,
  "status": 200,
  "data": {
    "task_id": "99e830a4-6c96-4ee1-ac9b-dcf04f37c71a"
  }
}
```

`cancel_review_task`（不存在的 id，业务性 404，`is_error=False`）：

```json
{
  "ok": false,
  "status": 404,
  "detail": {
    "error": "Task not found or already finished"
  }
}
```

> 同一路由直连 Flask 实测：`POST /api/review/outline` **0.097 s** → `{"task_id":"0b3d2257-5131-4ff0-9926-45b021310868"}`。

### 7.1 历史记录：单进程时代（2026-10-24 阶段三，`tools/list`）

```text
[selftest] tools.count  : 5
[selftest] tools        : ['get_abstract', 'get_paper', 'health', 'search_papers', 'task_status']
```

### 7.2 Flask 在跑（同上，单进程时代）

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

### 8.1 ~~`tasks` 表不存在~~ → **已不存在此问题**（2026-10-24 21:15 复核更正）

早期实测 `GET /api/tasks/<id>` 返回 500 `no such table: tasks`，**现已修复**：

| 检查 | 早期（已过时） | 现在实测 |
|---|---|---|
| `data/research.db` 是否有 `tasks` 表 | ❌ 不存在 | ✅ **存在**，11 列与 `services/unified_task_manager.py` 完全匹配 |
| `GET /api/tasks/<不存在的 id>` | 500 + traceback | **404** `{"error":"task not found"}` |
| tasks 表从哪来 | — | `api_server.py:2001` 启动时幂等创建（V33.12 统一任务表） |

> 结论：持久化任务表（`tasks`）是可用的。**两套任务体系共用同一张表，但端点不同**，
> 轮询时别拿错：
>
> | 体系 | 存储 | 端点 | 谁在用 |
> |---|---|---|---|
> | 在线下载 | SQLite `tasks` 表（`type='download_online'`） | `/api/tasks/<id>` | `download_online_papers` / `download_status` |
> | review 任务 | **同一张 `tasks` 表**（`type IN qa_ask/agentic_search/generate_outline/generate_review`，V33.17-6A 起持久化） | `/api/review/task/<id>` | `review_task_status` |
>
> ⚠️ **Review 任务自 6-A 起重启不丢**：轮询期间若 Flask 重启，任务会变成
> `status=failed` + `error="服务重启导致任务中断"`（**不再是 404**），已完成任务的
> `result` 也仍可查。启动时会把上次进程遗留的 review `running` 收成 `failed`
> （**只限上面 4 个类型，不碰 `download_online`**）；`/api/review/running_task`
> 同样只返回这 4 个类型，避免把下载任务误报成"综述在跑"。

### 8.2 其他

| 限制 | 说明 |
|---|---|
| 单次 HTTP 超时 45 s | 留 15 s 余量给 MCP 的 60 s 上限；更长的任务必须走 job 句柄 + 轮询 |
| `use_online=True` 可能超时 | 在线检索走 NCBI，网络慢时仍可能触及 45 s；纯在线检索用 `search_online`（默认每个库 20 条） |
| **重型能力（C-3 后）** | 已挂载且全部异步：`generate_outline`（C-1）、`generate_review`（C-2）、**`ask_question` / `agentic_search`（C-3，`POST /api/qa/ask_async` / `/api/agentic/search_async`）**。仍不挂：`papers/parse`（同步长任务）、`papers/import`（multipart，MCP 传不了文件流） |
| **检索栈重复加载（C-3 已修）** | `QAService` 曾自建一套 `UnifiedRetriever`，`/api/agentic/search` 曾**每次请求** new `AgenticSearcher`（其默认构造再建一套）→ 每次调用重建检索栈。实测 RSS **1124 → 3714 MB**、首次调用 **100.8 s**。C-3 起统一注入 `get_retriever()` 单例 |
| **冷启动会把请求循环饿住（一次性）** | 模型**首次加载**时（embedding / reranker，约 +1.5 GB，实测进程 1.47 → 2.94 GB），实测 `/api/health` 被饿到 **21.4 s / 21.8 s**。这是**冷启动一次性**，不是异步本身的问题：**模型热之后**，大纲任务跑完只要 5–7 s，同期连续 35 次 health 采样全在 **0.006 ~ 0.039 s**（2026-10-25 05:02 复测）。第一次用工具前先碰一下 health 或检索，把冷加载熬过去，再也不要套着 20 s 余量做设计 |
| ~~单线程 server 是真瓶颈~~ → **C-2 已修** | 原 `app.run(threaded=False)` 同一时刻只处理一个请求。C-2 改为 `threaded=True`，**且先补好两道安全阀**：① 异步任务每个 new 私有 `ReviewGenerator`（参数/中间结果不共享）；② 同步 `review/generate` 用 `_review_generate_lock` 串行化（共享单例仍安全）。实测并发两任务时 `/api/health` 0.058–0.132 s |
| **并发两个重任务会互相拖慢**（未修，属吞吐限制） | 实测同时提交两条综述任务（`max_papers=2`），两者在「检索文献」阶段停留数分钟（CPU / GIL 争抢 + 共享 retriever）。**不串台**（私有实例隔离生效），但**吞吐显著下降** —— 批量生成建议串行 |
| **解析入库不写 Chroma** | `DatabaseWriter.insert_paper()` 只写 `papers` / `paragraphs` / `figures` / `citations` / `tables`，**不写 ChromaDB** → 新解析的论文**不保证立刻被混合检索命中**（能按 `paper_id` 查详情、能进引用图谱）。要可检索需另跑索引构建脚本，不在 MCP 侧 |
| **MCP 不能上传 PDF** | `parse_paper` 只能解析 `documents/` 里**已存在**的文件；`/api/papers/import` 是 multipart，MCP 传不了文件流。新 PDF 仍需用户手工放入 |
| **docling 模型常驻进程（内存）** | 首次真解析会把 docling 模型载入 Flask 进程并**常驻**：实测 RSS **1123.6 → 2385.7 MB**（峰值 2762.3，**+1638 MB**）、Private **4764 → 7476 MB**（+2712 MB），任务结束后**不回落**。解析任务由 `_parse_lock` **串行化**（并发 = 双份内存），第二个任务的 progress 会显示「排队中（前面还有解析任务）」 |
| ⚠️ **本机解析入库当前失败于既有 FTS schema 缺陷** | `build_db/db_writer.py` 往 `paragraphs_fts` 插 `section_level1`，而该表实际列名是 `section_l1`（`paragraphs_fts` 只有 `para_id/paper_id/section_l1/section_l2/text`）→ `table paragraphs_fts has no column named section_level1`。**同步 `/api/papers/parse` 同样 500「解析成功但写入数据库失败」**（对照实验 13.7 s 复现），与本阶段改动无关。修复需改 `build_db/**`（本工单红线），建议单独开工单 |
| 长任务无同步等待 | DSH 不支持 task-based execution，本设计一律「立即返回句柄 + 轮询」（`download_online_papers` → `download_status`） |
| `search_hybrid` 结果体量 | 默认 `top_k=10`；大结果会占用较多上下文，按需调小 |
| 每 server ≤ 8 工具 | 约束是**模型上下文与选择准确率**，不是显存（MCP 进程不加载模型，≈68 MB/个） |
