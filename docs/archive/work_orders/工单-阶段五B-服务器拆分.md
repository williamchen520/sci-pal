# 工单 · 阶段五-B：MCP 服务器按业务流拆分（scipal-search / scipal-generate）

> 派单方：WorkBuddy（架构/验收）　执行方：CodeBuddy（代码）
> 创建：2026-10-24　父文档：`docs/阶段五-服务器拆分与bundle化.md` ｜ 路线图：`docs/DSH插件化-路线图.md`
> **本工单现在就执行**，不是"下一轮"。它是阶段五-A（bundle 化）之后的下一项，与阶段五-A 的提交不冲突
> （五-A 只新增 bundle 包与体检脚本，本工单动的是 `mcp_server/` 与 bundle 的 patch）。

---

## 零、背景事实（我已在本机仓库上现查核实，**直接采信，不要重复查**）

| 事实 | 证据 / 出处 |
|---|---|
| bundle `@local/dsh-scipal` **已于 19:40 安装进 `desktop` profile**，link 安装。改包内文件即生效，**不需要重装** | `~/.dsh/profiles/desktop/package.json` 的 `dependencies: "@local/dsh-scipal": "link:D:/sciPal/packages/dsh-scipal"`；`node_modules/@local/dsh-scipal` 为符号链接 |
| 重启后验通 6 个 `mcp__` 工具；进程层出现 2 个 stdio 子进程，父进程是 `DeepSeek Harness.exe` | 19:46:16 `scipal_server.py` + `mcp_ping_server.py` |
| profile patch `~/.dsh/profiles/desktop/cordis.patch.yml` 现为 916 B / 5 条 `- id:`，**无 insert、无 serverName** | 清场已完成，装 bundle 时也**没有**被写回 |
| 阶段三"只能单进程"的资源理由**已作废**：单 MCP server ≈ 68 MB（纯 urllib 转发，不加载模型），Flask ≈ 1123 MB（模型共享） | `docs/阶段五-服务器拆分与bundle化.md` §0 实测 |
| 现存两个 server：`mcp_server/scipal_server.py`（5 工具）+ `tests/mcp_ping_server.py`（哨兵 ping，零依赖） | 现查 |
| `toolCallTimeoutMs` 默认 **60000**；MCP **不支持** task-based execution | 官方 MCP 约束；`docs/DSH契约要点.md` |
| DSH 拉 stdio 子进程时会**清洗环境变量**（删 `/KEY\|PASSWORD\|SECRET\|TOKEN/i` 与 `DSH_*`） | `docs/DSH契约要点.md` |

**薄转发铁律（三条，违反即设计失效）**
1. 新 server **不 import 任何 SciPal 内部模块**（禁止 `from services...`、禁止 `import api_server`、禁止注入 sys.path 到项目根）。
2. **不改 Flask 业务代码、不新增 Flask 路由**。本工单 **零业务代码改动**。
3. stdio 模式下 stdout 是 JSON-RPC 通道，**绝不向 stdout 打印**。

**红线**：本工单**不得写 `~/.dsh` 下任何文件**（官方明令禁止手写 profile 的 `package.json` / `cordis.patch.yml`）。

---

## 一、🔴 范围发生改变：generate 侧本轮只能做"只读壳"

我把 generate 侧每条候选路由的实现读了一遍（`api_server.py` 对应 handler 全读了，不是猜的）：

| 候选能力 | 路由 | 实现方式 | 能否进 MCP |
|---|---|---|---|
| 综述生成 | `POST /api/review/generate` | **同步跑完整流水线**（检索→证据→大纲→撰写→引用校验），分钟级 | ❌ **不能**，远超 60s 且会阻塞 Flask |
| 大纲生成 | `POST /api/review/outline` | ✅ **自 V26.3 起已是异步**：立即返回 `{task_id}`，后台线程跑，配 `/api/review/task/<id>` 轮询 + `/api/review/cancel/<id>` 取消（实测 0.129 s 返回） | ✅ **能** —— 本工单当时漏判，留到五-C 挂载 |
| 多轮渐进式提问 | `/api/agentic/search` | 同步多跳（≤5 hops，每跳检索+LLM） | ❌ 至少数十秒，极易超时 |
| 问答 | `POST /api/qa/ask` | 同步 LLM | ❌ 同上（且依赖 Ollama） |
| PDF 解析 | `POST /api/papers/parse` | 同步解析（无 job 句柄） | ❌ |
| PDF 导入 | `POST /api/papers/import` | multipart 文件上传 | ❌ MCP 工具无法传文件流；且后续解析是同步的 |

**根因（2026-10-24 21:15 更正）**：除 `POST /api/review/outline` 与 `POST /api/search/download_online`
之外，Flask 侧其余重路由**都是同步阻塞**，没有 job 提交端点。
即：**已知的异步入口只有两个**，其余（`review/generate`、`agentic/search`、`qa/ask`、`papers/parse`）都需要异步化。

> ⚠️ 原文写「Flask 侧没有 job 提交端点」是**错的**：`api_server.py:527` 的
> `POST /api/review/outline` 自 V26.3 起就是 `task_manager.create_task()` + 后台线程 + 立即返回
> `{"task_id": ...}`，配套 `:599 /api/review/running_task`、`:612 /api/review/task/<id>`、
> `:628 /api/review/cancel/<id>` 全都在。**大纲生成因此是零业务改动可挂载的**（见阶段五-C）。

→ **本工单 `scipal-generate` 只做"只读 + 轮询"壳**
（读已生成的大纲/综述、查引用图谱、查任务状态），把重物留给 **阶段五-C：异步化**
（`POST /api/review/generate_async` 之类 + 写入 `unified_task_manager`）——那是**业务代码改动**，
需要用户单独点头，**不在本工单范围内，不要顺手做**。

---

## 二、B-1 · 抽公共薄转发层 `mcp_server/_forward.py`

把 `mcp_server/scipal_server.py` 里已验证可用的这 5 个东西**原样复制**过去，逻辑一个字都不要改：

- `base_url()`（读 `SCIPAL_BASE_URL`，默认 `http://127.0.0.1:5000`）
- `_not_running_error()`（给"装计划任务 / 等预热"的可操作指引，不在工具内同步起服务）
- `_http_raw()`（URLError → 受控 ToolError；4xx/5xx 交给调用方分流）
- `_call()`（2xx → `{"ok":true,...}`；4xx → `{"ok":false,"detail":...}`；5xx → ToolError）
- `_path_segment()`（`urllib.parse.quote(..., safe="")`）
- 常量 `HTTP_TIMEOUT_SECONDS = 45.0`（给 MCP 的 60s 留 15s 余量）

导入方式（**必须这样写**，否则 cwd 变化时 import 失败）：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _forward import _call, _path_segment   # noqa: E402
```

`mcp_server/scipal_server.py` **保留不动**（作为回退入口），可在文件头加一句 deprecated 注释说明它已被
`search_server.py` + `generate_server.py` 取代、暂勿删除。

---

## 三、B-2 · 新建 `mcp_server/search_server.py`（serverName `scipal-search`）

`MCPServer("scipal-search", version="0.1.0", instructions=...)`，`main()` 同样 `mcp.run(transport="stdio")`。

**必做 6 个工具**（参数名以 `api_server.py` 路由实际读取的为准，逐对照不许凭印象）：

| 工具 | HTTP | 路由 | 要点 |
|---|---|---|---|
| `health` | GET | `/api/health` | 与现有 `scipal_server.py` 的 health 完全一致 |
| `search_hybrid` | POST | `/api/search/hybrid` | body `{q, top_k, use_online}`（路由读的是 **`q` 不是 `query`**）；**`use_online` 默认 `false`**（默认 true 会联网，容易超 60s） |
| `search_online` | POST | `/api/search/online` | body `{q, max_results, search_pubmed, search_pmc}`，默认 `max_results=20` 别用 30（联网慢） |
| `get_paper` | GET | `/api/papers/<paper_id>` | 路径段必须 quote |
| `download_online_papers` | POST | `/api/search/download_online` | body `{pmc_ids: [...]}`；**立即返回 `task_id`**，description 必须写明"用 `download_status` 轮询" |
| `download_status` | GET | `/api/search/download_status?task_id=` | 已有实现，原样转发 |

**可选（做完必做 6 个之后再加，但工具总数 ≤ 8）**：
`list_local_papers`（GET `/api/papers/local`）、`list_abstracts`（GET `/api/abstracts/list`，参数 `page/page_size/search`）、
`get_abstract`（GET `/api/abstracts/<pmid>`，**按 PMID 查**，写进 description）、
`task_status`（GET `/api/tasks/<task_id>`，统一任务表）。

> 工具总数是有意设上限的。真正的约束不是显存，是**模型上下文**：工具越多模型选工具越差。宁可少而准。

---

## 四、B-3 · 新建 `mcp_server/generate_server.py`（serverName `scipal-generate`）

**必做 6 个工具**（全部只读 / 快速，不触发 LLM）：

| 工具 | HTTP | 路由 | 要点 |
|---|---|---|---|
| `health` | GET | `/api/health` | 与 search 侧同名但属不同 server（`mcp__scipal-generate__health`），这是分层诊断的一部分 |
| `list_saved_outlines` | GET | `/api/review/outline/saved` | 列出已保存大纲名 |
| `get_saved_outline` | GET | `/api/review/outline/saved/<name>` | name 必须 quote |
| `get_review` | GET | `/api/review/<review_id>` | 取已生成综述详情（含 sentences / evidence_cards） |
| `paper_citation_graph` | GET | `/api/papers/<paper_id>/graph` | 引用/被引/相似，论文级 |
| `review_task_status` | GET | `/api/review/task/<task_id>` | review 侧 TaskManager（与统一任务表不同，别混） |

**可选（总数 ≤ 8）**：`get_review_sentence`（GET `/api/review/<review_id>/sentence/<sentence_id>`）、
`graph_stats`（GET `/api/graph/stats`）、`running_review_task`（GET `/api/review/running_task`）。

> description 里必须写清"本 server 不触发任何生成；要生成综述/大纲需先有异步入口（见阶段五-C）"，
> 免得模型以为能用它生成东西。

---

## 五、B-4 · 自检 `mcp_server/selftest.py` 扩展

现有 selftest 只覆盖旧的 `scipal_server.py`。要求：

1. 参数化扩展为对 **3 个 server**（含新加的两个）逐个跑完整协议链路；
2. 每个工具至少一次真实 HTTP 调用（Flask 必须已起，否则**明确报"Flask 未启动"，不许报 PASS**）；
3. **逐个工具打印 PASS/FAIL**，最后汇总计数；不许 `try/except: pass`（这个项目已经栽过一次：
   `run_db_migrations` 缺 `import sqlite3` 被吞成"迁移跳过"）；
4. 中文输出注意 Windows 重定向可能抛 `UnicodeEncodeError`，必要时 `sys.stdout.reconfigure(encoding="utf-8")`。

---

## 六、B-5 · 更新 bundle 的 `packages/dsh-scipal/cordis.patch.yml`

**改动只在本文件**，共三条 MCP 条目：

1. **`mcp-scipalhello` 完全不动**（哨兵是诊断基准，删了就没法定位问题）；
2. **新增 `mcp-scipal-search`**（args → `D:/sciPal/mcp_server/search_server.py`）；
3. **新增 `mcp-scipal-generate`**（args → `D:/sciPal/mcp_server/generate_server.py`）；
4. **删除旧的 `mcp-scipal`**（否则与两个新 server 工具重复，白占模型上下文）。

每条**必须**照抄现有的 `mcp-scipal` 条目结构，尤其这几点：

- ❗ 新条目必须包在 **`- insert:` 块内**。写成顶层 `- id:` 会被判为 "targets that match no row"，**warn 后静默跳过**（这条踩过，见 `packages/dsh-scipal/cordis.patch.yml` 顶部注释）。
- `transport: stdio`、`command: 'D:/sciPal/venv_sciPal_py312/Scripts/python.exe'`（**必须用 venv 的 python**，系统 python 没有 `mcp` SDK）、`cwd: 'D:/sciPal'`。
- `env:` 必须带 `PYTHONUTF8: '1'`、`no_proxy: '127.0.0.1,localhost'`、`NO_PROXY: '127.0.0.1,localhost'`
  （本机有 `http_proxy=127.0.0.1:52819`，且 DSH 的 env 清洗**清不掉** `http_proxy` —— 不设会绕经代理，
  代理一挂 Flask 明明活着工具也会失败）。
- `toolCallTimeoutMs: 60000`。
- **`failOnStartupError: false`**（哨兵那条保持 `true` 不动）。
  理由：这个值若对某个 server 设 true，它启动失败会让整个 MCP client 拒绝激活，把哨兵也一起拖没，
  诊断能力归零。取 false 的代价是"失败不显式"——由哨兵 + 每个 server 的 `health` 工具 + 进程计数来兜。
  **不要把这个值"顺手改成 true"作优化。**
- 注释区更新：把文件末尾那段"工具出现形式"改成三条 server 的完整工具清单（含 `mcp__scipal-search__*` / `mcp__scipal-generate__*`）。

---

## 七、B-6 · 文档同步

1. `packages/dsh-scipal/README.md` 的工具清单换成新的 3 server 结构，并写一节 **「变更 bundle 后的生效方式」**：
   **link 安装 → 改包内文件即可，不必重装；但必须完全退出 DSH 再重启**（本机构型无 HMR，profile 只在启动时应用）。
2. `packages/dsh-scipal/INSTALL.md` 步骤 4 的期望清单同步更新，并补一句：
   新 server 挂载成功的硬判据 = 命令行含 `mcp_` 的 `python.exe` 进程总数**从 4 变成 6**
   （每条 server 命令都会出两层进程：venv 启动器 + 它 fork 的系统 python；
   现在 2 条命令 = 4 个进程，拆完 3 条命令 = 6 个进程，父进程链最终指向 `DeepSeek Harness.exe`）。
3. **README「还原」一节的过时数字顺手改掉**：现仍写"当前 profile 4209 字节 / 6 条顶层条目 / insert 在 64–98 行"，
   现状是 **916 B / 5 条 `- id:` / 无 insert / 无 serverName**。
   🔴 其中"`tests/cordis.patch.yml.bak`（297B）整体还原会抹掉 `ui-settings-account` 账户状态"这条风险提示**必须保留**。

---

## 八、明确不要做的事

- ❌ 不写 `~/.dsh/**` 任何文件
- ❌ 不改 `api_server.py`、不加路由、不动 Flask 业务代码（本工单零业务改动）
- ❌ 不做异步化端点（那是阶段五-C，要用户点头）
- ❌ 不 `import` SciPal 内部模块、不注入项目根到 sys.path
- ❌ 不删 `tests/mcp_ping_server.py` 和哨兵条目
- ❌ 不删除 `mcp_server/scipal_server.py`（保留作为回退）
- ❌ 不给现有 `app.py` / `config/settings.py` 之类的东西顺手做清理
- ❌ 不为"让测试通过"放宽断言

---

## 九、交接与验收（我要看到的证据）

1. `scripts/precheck_dsh_bundle.py` 的完整输出 —— 期望**退出码 0**
   （bundle 自身合法；profile 侧已无手写 serverName，不应有冲突；
   若报 `scipal-search` / `scipal-generate` 与谁冲突，说明 patch 写错了）。
2. `mcp_server/selftest.py` 的完整输出（**每个工具一行 PASS/FAIL + 汇总计数**，不要只贴最后一句）。
3. 逐工具的真实 HTTP 证据：对每个新工具用一次 curl 打它所对的 Flask 路由，
   返回 200（或业务性 404，如不存在的 id）即可，贴出 curl 与返回片段 —— 用来证明参数名和路径没写错。
4. 提交信息前缀用 `V33.17: 阶段五B 服务器拆分 —— `；**不要 `git add -A`**（仓库里有别人的未跟踪文件
   `_test_v3317b.py`），显式列路径；**不要自行 push**，由用户点名。
5. **交付报告里请明确回答**：`failOnStartupError` 三个 server 各是什么值、`env` 里 `no_proxy` 有没有写实、
   新条目是否都在 `- insert:` 块内 —— 这三处我一定会抽验。

patch 生效那一步由用户做（完全退出 DSH 再重启），之后我接手验证：会话里问工具清单 +
我这侧数 `python.exe` 里含 `mcp_` 的进程是否从 4 个变成 6 个（3 条命令 × 2 层进程）。
