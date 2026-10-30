# 工单 · 阶段六-A 任务持久化（review 任务 → SQLite）

> 提出：WorkBuddy ｜ 执行：CodeBuddy ｜ 2026-10-25
> 范围：**`services/review/task_manager.py` 重写 + `api_server.py` 一处启动对账**。不动路由响应、不动 schema。
> 规划：`docs/阶段六-规划与派单.md` §1。

---

## 零、背景事实（我已现查核实，**直接采信，不要重复查仓库**）

1. **现状**：`services/review/task_manager.py`（148 行）是纯内存 dict：
   `self._tasks: Dict[str, Dict]` + `threading.Lock`，模块级单例 `task_manager = TaskManager()`（`:148`）。
   **Flask 一重启全部丢失**。

2. **调用面很小，且只有 9 个方法**（我逐处 grep 过）：

   | 方法 | 调用方 |
   |---|---|
   | `create_task` | `api_server.py:329`（`"qa_ask"`）/`:444`（`"agentic_search"`）/`:687`（`"generate_outline"`）/`:1071`（`"generate_review"`） |
   | `get_task` | 路由 `:740` `GET /api/review/task/<id>` |
   | `get_running_task` | 路由 `:727` `GET /api/review/running_task` |
   | `cancel_task` | 路由 `:756` `POST /api/review/cancel/<id>`（另有 6 处内部调用） |
   | `complete_task` / `fail_task` | `api_server.py` 各 4 处 |
   | `is_cancelled` / `update_progress` | `services/review/review_generator.py` 各 4 处（`:266/487/499/515/522/543` 函数内 `from .task_manager import task_manager`） |

   → **只要这 9 个方法的签名与语义不变，`api_server.py` 与 `review_generator.py` 一行都不用改。**

3. **目标表已存在，且是空的**。`run_db_migrations()` 里建表（`api_server.py:2256-2268`）：

   ```sql
   CREATE TABLE IF NOT EXISTS tasks (
       task_id TEXT PRIMARY KEY, type TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'running',
       progress_text TEXT DEFAULT '', progress_pct REAL DEFAULT 0,
       params TEXT, result TEXT, error TEXT,
       created_at TEXT, started_at TEXT, finished_at TEXT
   )
   ```
   另有 3 个索引（`:2270-2272`：type / status / created）。**当前 `select count(*) from tasks` = 0 行**。
   11 列，**本工单不许改这个 DDL**。

4. **旧实现的精确语义**（新实现必须逐条对齐，表里是"内存行为"）：

   | 方法 | 行为 |
   |---|---|
   | `create_task(type)` | `uuid4()` 生成 id；`status="running"`；`progress="初始化中..."`；`result=None`；`error=None`；`cancelled=False` |
   | `get_task` | 返回**副本** dict（7 个键，见下）；不存在返回 `None` |
   | `cancel_task` | **仅当 `status=="running"`** → `cancelled=True` + `status="cancelled"`，返回 `True`；否则 `False` |
   | `complete_task` | **仅当 running** → `status="completed"` + `result=result` |
   | `fail_task` | **仅当 running** → `status="failed"` + `error=error` |
   | `is_cancelled` | 返回 `cancelled` 布尔；不存在返回 `False` |
   | `update_progress` | **仅当 running** → `progress=text` |
   | `get_running_task` | 第一个 `status=="running"` 的副本；无则 `None` |
   | `cleanup_old_tasks(max_count=100)` | 超量时删最早的（**全仓库无调用方**） |

5. 🔴 **API 契约 = `get_task()` 的 key 集合**。`:740` 的路由是 `return jsonify(task)` —— 直接把 dict 当响应，
   所以**返回的 7 个键就是对外契约**（前端在用，MCP 的 `review_task_status` 也直接透传）：

   ```
   task_id / task_type / status / progress / result / error / cancelled
   ```

   而表里的列名是 `type` / `progress_text` → **必须映射**，否则前端与 MCP 同时断。

6. **`services/unified_task_manager.py` 已有同表封装，但不能直接复用写函数**。它的
   `complete_task`(`:61`) / `fail_task`(`:74`) / `cancel_task`(`:87`) 的 SQL **不判 `status`**
   （无条件 UPDATE）。而旧 review 语义是"仅 running 生效" —— 直接复用会导致
   **已取消的任务被后续线程改成 completed**（取消就白取了）。`update_progress`(`:49`) 恰好带
   `WHERE status='running'`，只有它条件对。
   → 结论：**自己写 SQL**（条件逐条对齐），不要 import `unified_task_manager`
   （它还带 SSE `_broadcast`，review 路由不用，引入只会多一层耦合）。

7. **DB 路径不要用相对路径**。`unified_task_manager.py:19` 是 `DB_PATH = Path("data/research.db")`
   （依赖 cwd，计划任务/别处启动就会写错库）。`api_server.py:20/26` 的做法是对的：
   `PROJECT_ROOT = Path(__file__).parent` + `DB_PATH = PROJECT_ROOT / "data" / "research.db"`。
   → 适配器里用 `Path(__file__).resolve().parents[2]` 推出项目根，**不要照抄相对路径**。

8. **另两套任务 id 风格并存**：`unified.create_task` 生成 `task_<hex12>`，`online_downloader` 在用
   （`services/search/online_downloader.py:237/276/320`，type 形如 `download_online`）。
   **本工单不许改它们**；review 侧继续用 `uuid4()`（36 字符），保持既有 id 形态不变。

9. **当前基线**：`mcp_server/selftest.py` **3 server / 25 断言 / 25 PASS**；
   `scripts/precheck_dsh_bundle.py` 退出码 0；Flask 单实例由计划任务 `SciPalWatchdog` 托管
   （killed 后约 30~110 s 自愈，冷启动慢是正常的）。

---

## 一、为什么要做（两个真实后果）

1. **MCP 侧会误判任务失败**。DSH 里模型拿到 `task_id` 后，只要 Flask 重启过（看门狗拉起、
   改代码重启 —— 今天上午就发生多次），轮询就是 `404 Task not found`，模型只能判定"任务失败"。
2. **重启后完全无法回溯**：历史综述/大纲结果查不到，`/api/review/running_task` 永远空。
   而 `tasks` 表本来就是为"重启不丢失"建的（`unified_task_manager` 的 docstring 原话），
   review 侧却没接进去 —— 这是**两套任务体系分叉**的遗留。

---

## 二、目标 / 非目标

**目标**：`services/review/task_manager.py` 换成 SQLite 适配器，
**9 个方法签名、7 键返回、条件语义三者全不变**；重启后能查到历史任务，僵尸 running 被收尸。

**非目标**：
- 不改 `tasks` 表结构、不改索引；
- 不改任何路由的响应字段与状态码；
- 不动 `online_downloader` / `unified_task_manager` 的现有行为；
- 不做任务列表 UI、不做 SSE。

---

## 三、任务

### A-1 重写 `services/review/task_manager.py` 为 SQLite 适配器

- 保持：类名 `TaskManager`、9 个方法签名、模块级单例名 `task_manager`（`api_server.py:24` 的 import 不能变）。
- 每次操作**新建连接、短生命周期**（与 `unified_task_manager` 一致），
  `sqlite3.connect(str(DB_PATH), timeout=5)` —— **必须带 timeout**：后台线程 + 路由线程会并发写，
  默认 5 s 内不重试会直接抛 `database is locked`。
- `row_factory = sqlite3.Row`。
- `LOGS_DIR` 无关；DB 路径按 §0.7 的绝对路径做法。

### A-2 字段映射（最容易做错的一处）

| 返回键 | 来源 |
|---|---|
| `task_id` | `task_id` |
| `task_type` | **`type`** |
| `status` | `status` |
| `progress` | **`progress_text`** |
| `result` | `result`（TEXT，`json.loads` 还原） |
| `error` | `error` |
| `cancelled` | **派生** `status == "cancelled"`（表里没有这一列） |

- 写入时 `result` 用 `json.dumps(..., ensure_ascii=False)`；`None` 写 `NULL`。
- 🔴 **`json.loads` 失败必须降级为原始字符串返回，不能抛** —— 否则一条脏数据会让整个
  `/api/review/task/<id>` 500。
- `get_task` 返回的**键必须恰好这 7 个**，不要顺手把 `created_at` / `params` 也加进去
  （加字段会改变前端/MCP 看到的 JSON，属未授权变更）。

### A-3 条件语义对齐（第二处易错）

- `cancel_task` / `complete_task` / `fail_task` / `update_progress` 的 SQL 都要带
  `WHERE task_id = ? AND status = 'running'`，用 `cursor.rowcount` 判断是否真的生效
  （`cancel_task` 的返回值必须是"是否真的取消成功"，路由靠它给 404）。
- `complete_task` 在已 `cancelled` 的任务上**必须无效** —— 后台线程跑完仍会调 `complete_task`，
  若覆盖状态，用户明明取消了却显示完成。
- `complete_task` 建议同时把 `progress_pct` 置 100、写 `finished_at`（不影响对外的 7 个键）。

### A-4 启动对账（僵尸任务收尸）

Flask 启动时，把**上一次进程遗留的 `status='running'` 收掉**，否则重启后
`/api/review/running_task` 永远返回一条永远不动的任务，新任务也被前端误认为"还在跑"。

- 位置：`api_server.py` 的 `run_db_migrations()` 之后（启动期，一次）；
- **范围必须限定在 review 的 4 个类型**：`qa_ask` / `agentic_search` / `generate_outline` / `generate_review`
  —— **不许动** `download_online` 等其它类型（那是 `online_downloader` 的地盘）；
- 动作：`status='failed'` + `error='服务重启导致任务中断'` + `finished_at=now`；
- **幂等**：没有 running 行时什么也不做；重复启动不报错；
- 打一行启动日志（含收尸条数），方便下次从 `logs/sciPal_api.log` 复现。

### A-5 文档（同批提交）

- `mcp_server/README.md` 里「两套任务体系」的段落改为**现状**：
  review 任务现与 `download_online` 同表（`tasks`），重启不丢；轮询期间若服务重启，
  任务会变成 `failed`（error 含"中断"）而不是消失。
- `docs/阶段六-规划与派单.md` §1 的"现状"补一行完成标记（不要重写整节）。

---

## 四、验收（我这边会这么跑，你可以先自查）

| # | 检查 | 判据 |
|---|---|---|
| 1 | **重启持久化**（核心） | 提交 `POST /api/review/outline` 拿 `task_id` → **立刻 kill 掉监听 5000 的进程** → 等 `/api/health` 200（看门狗自愈，30~110 s 正常）→ 再用同一 `task_id` 轮询：**HTTP 200 + `status=failed` + `error` 含"中断"**，**不是 404** |
| 2 | 无僵尸 | 重启后 `GET /api/review/running_task` → `{"running": false}` |
| 3 | **对账范围正确** | 我手工插一条 `type='download_online', status='running'` 的记录 → 重启 → 该行**仍是 running**（不许被 review 的对账顺手改掉） |
| 4 | 响应形状不变 | `/api/review/task/<id>` 返回的 key 集合**恰好** `task_id/task_type/status/progress/result/error/cancelled`（贴出真实 JSON） |
| 5 | 条件语义 | 任务 `completed` 后 `POST /api/review/cancel/<id>` → **404**；已 `cancelled` 的任务再被 `complete_task` → 状态**仍为 cancelled** |
| 6 | 并发不串 | 同时提交 2 个 outline（不同 topic）→ 两条各自 running、progress 各走各的；取消 A → A=cancelled，**B 仍 running 并最终 completed** |
| 7 | 回归 | `mcp_server/selftest.py` **25/25 PASS**，`leftover_tasks=0`；`precheck` 退出码 0 |
| 8 | schema 未动 | `PRAGMA table_info(tasks)` 与改动前**完全一致（11 列）** |

> 第 1 项要"立刻 kill"：提交后 0.1~0.5 s 就杀，确保任务还在 running。
> 若任务恰好已完成，重跑一次即可。

---

## 五、交付报告必须回答（我会抽查）

1. **你复用 `unified_task_manager` 还是自己写 SQL？为什么？**
   （预期：自己写，理由见 §0.6 —— 它的 complete/fail/cancel 不判 running）
2. `get_task()` 返回的**真实 JSON**（贴一个完成任务的完整返回），并说明 key 集合与旧实现是否一致。
3. **启动对账**的实现位置、SQL 原文、幂等做法、以及"只影响 4 个类型"是怎么限定的。
4. **重启测试的实际输出**：提交 → kill → 恢复 → 轮询，把每一步的命令与返回贴出来。
5. `git diff --stat`，以及 `PRAGMA table_info(tasks)` 的列数（应为 11）。

---

## 六、红线

- **不许改 `tasks` 表结构 / 索引**；
- **不许改 4 个路由的响应字段与状态码**（`/api/review/task/<id>`、`/running_task`、`/cancel/<id>`，
  以及 `outline`/`generate`/`qa/ask_async`/`agentic/search_async` 的返回体）；
- **不许改 `mcp_server/**`**（本阶段工具数不变，18）；
- **不许动** `services/unified_task_manager.py` / `services/search/online_downloader.py` 的现有行为；
- 不许改 `UnifiedRetriever.retrieve()` / `HybridRetriever.search_papers()` 签名；不许改 `research.db` 其它表；
- 不许 `git add -A`（仓库里有别人的 `_test_v3317b.py`），显式列路径；
- 提交前缀 `V33.17: 阶段六A 任务持久化 —— `；**不要自己 push**。

---

## 七、一句话

这一条的价值不在"存到库里"，而在于：**模型在 DSH 里拿到的 `task_id` 从此是一个不会因为服务重启而消失的句柄** ——
失败也要有个明确的 `failed`，而不是 404。
