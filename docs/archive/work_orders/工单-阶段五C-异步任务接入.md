# 工单 · 阶段五-C：异步任务接入 MCP（大纲生成链路）

> 派单方：WorkBuddy ｜ 执行方：CodeBuddy ｜ 生成时间：2026-10-24 21:20
> 前置：阶段五-B 已验收通过（dev `5c53bd3`，13 个工具在线）
> 本工单**只做 C-1**。C-2 是业务代码改动，**等用户单独点头，不要顺手做**。

---

## 零、背景事实（我已在本仓库现查核实，**直接采信，不要重复查**）

1. **`POST /api/review/outline` 自 V26.3 起就是异步的**（`api_server.py:527`）：
   `task_manager.create_task()` → `threading.Thread` 跑 → **立即** `return jsonify({"task_id": task_id})`。
   实测（Flask 在跑、topic=CRISPR delivery、max_papers=2）：**0.129 s 返回** `{"task_id":"6662334d-…"}`。
   → 这条链路**零业务改动**就能接进 MCP，五-B 当时误判成"同步"。

2. 配套端点齐全（都在 `api_server.py`）：
   | 端点 | 行号 | 作用 |
   |---|---|---|
   | `GET /api/review/task/<task_id>` | 612 | 轮询状态：`status` = running/completed/failed/cancelled，含 `progress`、`result`、`error`、`cancelled` |
   | `GET /api/review/running_task` | 599 | 查当前是否有运行中任务（刷新恢复用） |
   | `POST /api/review/cancel/<task_id>` | 628 | 取消 |

3. **review 任务存在进程内内存 dict**（`services/review/task_manager.py`：`self._tasks: Dict`），
   **不落库、重启即丢**。所以：Flask 重启后旧 `task_id` 一律查不到（返回 404 `{"error":"Task not found"}`），
   这不是 bug，工具 description 里要写明。

4. **另一套任务体系是持久的**：`services/unified_task_manager.py` + SQLite `tasks` 表
   （`api_server.py:2001` 启动时幂等建表，实测表已存在、11 列）。`GET /api/tasks/<id>` 现返回
   **404**（不再是早期文档写的 500）。在线下载工具 `download_status` 用的是这套。
   → **两套不能混用**：大纲生成的任务 id **只能**查 `/api/review/task/<id>`。

5. **`app.run(..., threaded=False)`**（`api_server.py:2057`）—— Flask 是**单线程**。
   实测：大纲任务运行期间，`GET /api/health` 被饿到 **21.4 s / 21.8 s**；任务结束后立刻回到 **0.03 s**。
   → 轮询不要设成秒级连打；MCP 侧 45 s 的 HTTP 超时**够用但没余量**，工具 description 要提示
   「轮询间隔建议 ≥5 s」。

6. `POST /api/review/generate`（`:791`）**是同步的**，一次返回整篇 `markdown`，**无 task_id**。
   异步化属 **C-2**，本工单不做。

7. `POST /api/agentic/search`、`POST /api/qa/ask`、`POST /api/papers/parse` 也都是同步；
   `POST /api/papers/import` 是 multipart，MCP 传不了文件流。**本工单都不碰。**

8. MCP 侧硬约束不变：`toolCallTimeoutMs = 60000`、**不支持 task-based execution**、
   stdio 子进程 env 会被清洗（`/KEY|PASSWORD|SECRET|TOKEN/i` 与 `DSH_*` 全删）、
   **绝不向 stdout 打印**。

9. 当前工具数 **13**（`scipal-search` 6 + `scipal-generate` 6 + 哨兵 1）。
   本工单加 2 个 → **15**，`scipal-generate` 变成 **8**，**正好卡在上限**，不要再加。

---

## 一、范围

### C-1（本工单，零业务改动）

只改 `mcp_server/generate_server.py` + `mcp_server/selftest.py` + **文档**。
**不许改 `api_server.py` / `services/**` 任何一行。**

新增 2 个工具：

| 工具名 | 路由 | 入参 | 返回 |
|---|---|---|---|
| `generate_outline` | `POST /api/review/outline` | `topic`(必填) / `max_papers`=20 / `review_type`="narrative" / `language`="en" | `{"task_id": "..."}` —— **立即返回** |
| `cancel_review_task` | `POST /api/review/cancel/<task_id>` | `task_id`(必填) | 成功 `{"success":true}`；不存在/已结束 → 404 |

`review_task_status`（已有）就是这两个的**轮询入口**，不要重复造。

### C-2（**不在本工单范围**，只写预研结论，等用户点头）

见第三节。**一行代码都不要动。**

---

## 二、C-1 任务分解

### C-1.1 `generate_outline`

```python
@mcp.tool(
    description=(
        "生成综述段落级大纲（POST /api/review/outline）。"
        "**立即返回 task_id，不要同步等待**；用 review_task_status 轮询，建议间隔 ≥5s。"
        "任务存在 Flask 进程内存里，Flask 重启后 task_id 会失效（返回 404）。"
        "review_type: narrative|comparative|systematic；language: en|zh。"
    )
)
def generate_outline(topic: str, max_papers: int = 20, review_type: str = "narrative", language: str = "en") -> str:
    ...
```

- 转发走 `_forward._call("POST", "/api/review/outline", {...})`，**不要**自己拼 requests。
- **参数名必须原样透传**：`topic` / `max_papers` / `review_type` / `language`
  （这几个 Flask 侧就是这几个名字，**没有** `q` 那种映射）。
- 返回体**直接透传** `{"task_id": ...}`，不要包装成 `{"ok": true, "task_id": ...}` ——
  与 `download_online_papers` 的既有风格保持一致，模型侧好判读。

### C-1.2 `cancel_review_task`

- `POST /api/review/cancel/<task_id>`，`task_id` 走 `_path_segment()`（防注入，和 `get_paper` 一致）。
- 404 语义：`{"error": "Task not found or already finished"}` —— 这是**业务结果**，按既有约定
  `is_error=False`（参 `README.md` §7.2：4xx 按业务结果返回）。

### C-1.3 selftest 扩展

- `scipal-generate` 期望工具数 **6 → 8**。
- 新增 2 条断言（总断言 **20 → 22**）：
  - `generate_outline`：真实调用，断言返回**含 `task_id` 且耗时 < 10 s**（这是「异步」的判据，
    不是看 `is_error`）——`max_papers` 给 1~2，避免真跑重活。
  - `cancel_review_task`：用一个**不存在**的 task_id，断言 `status=404`（业务错误算通过）。
- 不许 `except: pass`；每条断言要打印 PASS/FAIL 与关键字段。

### C-1.4 文档同步

1. `mcp_server/README.md`
   - §5.2 表格加这 2 个工具（`scipal-generate` 6 → 8）
   - §5 开头的「13 个」→ **15 个**
   - §7.0 自检记录更新（断言 22）
2. `packages/dsh-scipal/README.md` / `INSTALL.md`：工具清单与「13 个」→「15 个」
3. `packages/dsh-scipal/cordis.patch.yml` 顶部注释里的工具数（若有）

> 数字要**全仓库一致**：五-B 已经因为「17 vs 13」被打回过一次，别再犯。
> 自查命令：`grep -rn "13 个\|15 个\|1[0-9] 个 mcp" mcp_server/README.md packages/dsh-scipal/`

### C-1.5 bundle 挂载

**不需要改 `cordis.patch.yml`**（工具增加不改 serverName）。bundle 是 link 安装，
改 `generate_server.py` 后**完全重启 DSH** 即生效，不用重装。

---

## 三、C-2 预研结论（**只记录，不实施**）

要让 `review/generate`（分钟级）、`agentic/search`、`qa/ask` 进 MCP，必须先在 Flask 侧造
「提交即返 + 可轮询」的入口。两条路：

| 方案 | 做法 | 代价 | 实测风险 |
|---|---|---|---|
| **A 线程** | 复制 `outline` 的写法：`task_manager` + `threading.Thread` + 立即返 task_id（新端点 `POST /api/review/generate_async`） | 小，与既有代码同构 | **`threaded=False` + GIL 争用**：实测大纲任务跑时 `/api/health` 饿到 **21.8 s**。若轮询也踩在同一时窗，会连续超时；且任务重启即丢 |
| **B 子进程**（推荐） | 重任务交给独立 `subprocess`（或 `multiprocessing`）进程，进度与结果写 SQLite `tasks` 表；MCP 用 `/api/tasks/<id>` 轮询 | 大：要动 `unified_task_manager` 的写入方 + 任务类型注册 | 进程隔离，Flask 永远秒回；任务跨 Flask 重启可查（持久）。但**模型加载会在子进程里再来一份**（约 +1.5 GB），8 GB 卡要评估 |

**另外无论选哪条，都要单独确认一件事**：`app.run(threaded=False)` 是否要改成 `True`。
单线程意味着**任何**同步重路由（现在就有 5 个）都会把健康检查饿死 ——
这和 MCP 的 60 s 超时叠加，是线上最容易踩的坑。改它是**运行模式变更**，影响所有路由，需用户点头。

---

## 四、硬要求（沿用五-B，逐条自查）

1. `mcp_server/*.py` 仍是**纯 HTTP 客户端**：不许 `from services...`、不许 `import api_server`、
   不许把项目根塞进 `sys.path`（只允许把 `mcp_server/` 自己塞进去 import `_forward`）。
2. **绝不 `print()`** 到 stdout（stdio 是 JSON-RPC 通道）。
3. 用 `_forward.py` 现成的 `_call` / `_path_segment`，**不要重复实现 HTTP 层**，
   也不要改 `_forward.py` 的既有行为。
4. **不许改 `api_server.py` / `services/**`**（本工单零业务改动）。
5. **不许 `git add -A`**（仓库里有别人的 `_test_v3317b.py`，未跟踪，别动）。
6. 提交信息前缀：`V33.17: 阶段五C C-1 —— `，**不要自己 push**。

---

## 五、验收判据（WorkBuddy 会独立复跑，不看你的报告）

| 判据 | 期望 |
|---|---|
| `precheck_dsh_bundle.py` | 退出码 **0**（3 条 insert 不变） |
| `selftest.py` | **4 server / 22 断言 / 全 PASS / exit 0**，`scipal-generate` 期望 8 个工具 |
| `generate_outline` 真实耗时 | **< 10 s** 返回且含 `task_id`（异步判据） |
| 薄转发铁律 | `grep "from services\|import api_server"` 在 3 个 server 里 **0 命中**；`grep "print("` **0 命中** |
| 业务代码零改动 | `git diff --stat origin/dev..HEAD` 里**不得出现** `api_server.py` / `services/**` |
| 文档数字一致 | 全仓库「15 个」一致，无残留「13 个」 |
| 重启后 | 工具 **15 个**，含 `mcp__scipal-generate__generate_outline` |

---

## 六、交付报告必须明确回答（我会抽验）

1. `generate_outline` 实测**返回耗时**是多少？返回体原文贴出来。
2. `review_task_status` 用的是哪一套任务体系？`/api/tasks/<id>` 还是 `/api/review/task/<id>`？为什么？
3. 你有没有动 `api_server.py` 或 `services/`？贴 `git diff --stat` 原文。
4. 全仓库搜「13 个」的结果是什么？如果还有残留，在哪里、为什么可以留？
