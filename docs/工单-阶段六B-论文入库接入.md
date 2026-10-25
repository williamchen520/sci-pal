# 工单 · 阶段六-B 论文入库链路接入 MCP

> 提出：WorkBuddy ｜ 执行：CodeBuddy ｜ 2026-10-25
> 范围：**1 个新异步端点 + 2 个 MCP 工具 + 任务类型扩展**。不碰解析器、不碰检索索引、不碰 schema。
> 规划：`docs/阶段六-规划与派单.md` §2。

---

## 零、背景事实（我已现查核实，**直接采信，不要重复查仓库**）

1. **`POST /api/papers/parse`（`api_server.py:1655`）收 JSON body 的 `filename`，不是 multipart。**
   已做路径穿越校验（`".."` / `/` / `\\` 一律 400），文件必须在 `documents/` 目录下。
   → 所以 MCP **可以直接传文件名**，不需要文件流。multipart 的只有 `/api/papers/import`（那个不做）。

2. **`GET /api/papers/local`（`:1188`）** 扫描 `documents/` 下所有 PDF 并交叉查 `papers` 表，返回：

   ```
   { total, parsed_count,
     papers: [{filename, file_size, file_size_mb, modified_at,
               parsed, paper_id, title, authors, year,
               paragraph_count, supp_count}] }
   ```
   当前 **77 篇，全部已解析**（`parsed=true`，`papers` 表 565 行）。

3. **解析是同步的，且慢**。我 2026-10-25 13:15 用 `ParserOrchestrator` 直接跑了两次
   （临时副本、**未写库**，脚本已删）：

   | 文件 | 大小 | 构造 `ParserOrchestrator()` | `parse_paper()` |
   |---|---|---|---|
   | `PMC12707946.pdf` | 6.3 MB | **2.5 s** | **23.9 s**（85 段 / 7 图） |
   | `PMC12707966.pdf` | 3.1 MB | 2.5 s | **11.7 s**（76 段 / 7 图） |

   → **约 3.8 s/MB**。推外推：10 MB ≈ 38 s，**16 MB 以上就会顶穿 MCP 的 60 s 上限**。
   所以必须异步；这不再是"可能超时"，是"大文件必然超时"。

4. **构造器只要 2.5 s**，说明 docling 模型是懒加载／进程内复用；解析本身是主要成本。
   ⚠️ 但**首次解析会把 docling 模型加载进 Flask 进程**（内存增长未测，需你实测并报告，见 §四.6）。

5. **入库写哪些表**：`DatabaseWriter.insert_paper()`（`build_db/db_writer.py:38`）——
   `papers` 元数据 + `paragraphs` + `figures` + `citations` + `tables`。
   **不写 ChromaDB**（该文件里没有任何 chroma/embed 引用）。
   → 后果：**解析入库 ≠ 立刻能被混合检索命中**（`services/search/hybrid_search.py:67` 读的是
   Chroma 持久化集合）。本工单**不解决索引**，只要求在 README 里如实写明这条限制。

6. **下载链路和解析链路是两条**：`online_downloader` 把 PMC **XML** 存到 `documents_xml`
   （`services/search/online_downloader.py:40`），不是 PDF。所以 `documents/` 里的 PDF
   **只能由用户手工放入** —— MCP 侧无法上传新 PDF，这是真实限制，不要假装能传。

7. **6-A 刚做完的持久化可以直接复用**：`services/review/task_manager.py` 已是 `tasks` 表适配器，
   `create_task(type)` / `update_progress` / `is_cancelled` / `complete_task` / `fail_task` 都在，
   任务跨重启可查。**新任务的 task_id 用 `review_task_status` 就能轮询**（同一个 `/api/review/task/<id>`）。

8. **6-A 的类型白名单要扩**。`services/review/task_manager.py:44` 与
   `api_server.py` 的 `REVIEW_TASK_TYPES`（各一份，值必须一致）目前是 4 个类型：

   ```python
   ("qa_ask", "agentic_search", "generate_outline", "generate_review")
   ```

   这个白名单同时决定 **启动对账**（收僵尸）与 `/api/review/running_task` 的范围。
   新的 `parse_paper` 不进去 → **重启后遗留的解析任务会永远 running**，新任务也不算在途。

9. **异步端点的现成模板**：`/api/review/generate_async`（`api_server.py:1024`）——
   `task_manager.create_task(...)` → 内部 `def run_task()` → `threading.Thread(daemon=True).start()`
   → 立即 `jsonify({"task_id": task_id})`。照这个写即可。

10. **当前基线**：18 个工具（哨兵 1 + search 8 + generate 9）；`selftest` 3 server / **25 断言**；
    `precheck` 退出码 0；Flask 单实例由 `SciPalWatchdog` 托管。

---

## 一、目标 / 非目标

**目标**：模型在 DSH 里能自己完成「**看有哪些 PDF 没入库 → 挑一个解析入库 → 轮询进度 → 拿 paper_id**」
这一小段闭环，不用回 Web UI 点。

**非目标（明确不做）**：
- ❌ 不做 PDF 上传（multipart 走不了 MCP；新 PDF 仍由用户放进 `documents/`）；
- ❌ 不做 Chroma 索引重建（新入库的论文**不保证立刻被混合检索命中**，只保证能按 `paper_id` 查到详情）；
- ❌ 不改 `ParserOrchestrator` / `DatabaseWriter` 任何逻辑；
- ❌ 不改同步 `/api/papers/parse`（前端在用）；
- ❌ 不新增 server（工具加到 `scipal-search`）。

---

## 二、任务

### B-1 新异步端点 `POST /api/papers/parse_async`

- 参数与同步版一致：`filename`（JSON body）。
- **便宜校验同步做，昂贵工作异步做**（这条很重要）：
  - `filename` 为空 → **400**；含 `..` / `/` / `\` → **400**；
  - `documents/<filename>` 不存在 → **404**；
  - 以上都在**返回 task_id 之前**判掉 —— 让模型立刻知道参数错了，而不是拿到一个注定失败的任务；
- 校验通过后 `task_manager.create_task("parse_paper")`，后台线程里：
  1. 再查一次 `papers.filename` 是否已解析 → 是则 `complete_task` 返回
     `{"status": "already_parsed", "paper_id": ..., "title": ..., "paragraph_count": ...}`（**秒级完成**）；
  2. 否则 `ParserOrchestrator().parse_paper(path)` + `DatabaseWriter().insert_paper(...)`；
  3. 成功 → `complete_task` 返回 `{"status":"parsed","paper_id","title","paragraph_count","stats":{...}}`
     （字段与同步版**保持一致**，前端那份结构可以直接对照）；
  4. 失败 → `fail_task(task_id, 错误摘要)`（`str(e)[:500]` 即可，别把整段 traceback 塞进 DB）。
- **进度上报**：至少三个阶段 —— `排队中…` / `解析中（docling）…` / `写入数据库…`。
- 🔴 **并发串行化**：加一把模块级 `_parse_lock = threading.Lock()`，
  拿不到锁时先 `update_progress(task_id, "排队中（前面还有解析任务）")` 再 `acquire()`。
  理由：docling 模型在**进程内**加载，两个解析并发 = 双份内存 + 抢 CPU，而解析本来就是分钟级，
  排队完全可接受。**不要**为了"看起来更快"去掉这把锁。

### B-2 任务类型扩展（改 6-A 的两处白名单）

- 把 `parse_paper` 加进白名单，并**顺手把名字改准**：`REVIEW_TASK_TYPES` → **`PERSISTED_TASK_TYPES`**
  （现在它管的不止 review 了），两个文件同步改：
  - `services/review/task_manager.py`（`:44`）
  - `api_server.py`（`reconcile_stale_review_tasks` 上方）
- 改完必须满足：① 启动对账会收掉遗留 `parse_paper` 的 running；② `/api/review/running_task`
  能看到正在跑的解析任务；③ **仍然不包含 `download_online`**。
- 别把这两个常量写成两套不同的值 —— 现在就是"两处硬编码必须一致"，改的时候一起改，
  并在两边注释里写明「另一份在 <文件>，必须同步」。

### B-3 MCP 工具（`scipal-search` 8 → 10）

| 工具 | 转发 | 说明要点 |
|---|---|---|
| `list_local_papers(only_unparsed: bool = False, limit: int = 20)` | `GET /api/papers/local` | 77 篇全量返回对模型上下文太重：**默认只回 `filename/parsed/paper_id/title/file_size_mb/paragraph_count`**，并额外给 `total` / `parsed_count` / `unparsed_count`；`limit` 截断并在结果里标注"已截断，共 N 篇" |
| `parse_paper(filename: str)` | `POST /api/papers/parse_async` | 描述里**必须写清**：① 只能解析 `documents/` 里已有的 PDF，本工具**不能上传**；② 返回 `task_id`，用 `mcp__scipal-generate__review_task_status` 轮询；③ 大文件解析可能几分钟 |

- 两个工具都走 `_forward.py` 现有的 `_call` / `_path_segment`，**不许自己拼 urllib**。
- 工具描述不要写"保证可检索" —— 见 §零.5 的限制。

### B-4 selftest 扩展（25 → 27 断言）

- `list_local_papers`：200 且返回体含 `total` / `papers`（业务错误算通的口径不变）。
- `parse_paper` 异步判据：**返回耗时 < 10 s 且 `task_id` 非空**；
  然后**立刻用 HTTP 取消它**（走 `mcp_server/selftest.py` 现有的 HTTP 清理通道，不要再走工具），
  并在汇总里体现 `清理失败` / `leftover_tasks`（沿用 6-A 已有的统计）。
  > 选一个**已解析**的文件（如 `PMC12707946.pdf`）来测：它走 `already_parsed` 快路径，
  > 不会真的跑 docling，也不会往库里写垃圾数据。

### B-5 文档

- `mcp_server/README.md`：工具清单 18 → **20**（search 8 → 10），
  并在「已知限制」补两条：① 解析入库不写 Chroma，**不保证立刻被混合检索命中**；
  ② MCP 不能上传 PDF，只能解析 `documents/` 里已有的文件。
- `packages/dsh-scipal/README.md` + `INSTALL.md` + `cordis.patch.yml` 顶部注释：工具数 18 → **20**。
- `docs/DSH插件化-路线图.md` §2.4 的 `papers/parse` 行 → 标「已完成（6-B）」。
- `docs/阶段六-规划与派单.md` §2 标完成。

---

## 三、验收（我这边会这么跑，你可以先自查）

| # | 检查 | 判据 |
|---|---|---|
| 1 | 工具数 | 20 个：哨兵 1 + search **10** + generate 9；`selftest` 3 server / **27 断言**全 PASS |
| 2 | 异步判据 | `parse_paper` 返回 **< 10 s** 且带 `task_id` |
| 3 | 快路径 | 用**已解析**文件调用 → 轮询很快 `completed`，返回 `status=already_parsed` + 真实 `paper_id` |
| 4 | **参数校验是同步的** | 空 filename → 400；`../x.pdf` → 400；不存在文件 → **404**（**不是**返回 task_id 再失败） |
| 5 | **真解析端到端**（我自测，用副本） | 我复制一个 PDF 为临时文件名 → 异步解析 → 轮询至 completed → `paragraph_count > 0`；**然后我会删掉该 paper 的 `papers`/`paragraphs`/`figures`/`citations` 行与临时 PDF**，不留垃圾 |
| 6 | **内存影响** | 报 Flask 进程解析前后的 RSS/Private（任务管理器里第一次解析会把 docling 模型载进进程）。若增长 > 1 GB，我要在限制里写明 |
| 7 | 对账范围 | 手工插一条 `type='parse_paper', status='running'` + 一条 `download_online` running → 重启 → **前者被收成 failed、后者仍 running** |
| 8 | 排队锁 | 连续提交 2 个解析任务 → 第二个的 progress 出现 `排队中`，且**不会**同时跑两个 docling |
| 9 | 回归 | 同步 `/api/papers/parse`（前端用）行为不变；`precheck` 0；`running_task` 不返回 `download_online` |

---

## 四、交付报告必须回答

1. `parse_async` 的**校验顺序**：哪些错误在返回 task_id 前判掉？贴代码片段。
2. **真解析一次**的端到端耗时（从提交到 `completed`），以及 `paragraph_count` / `figures` / `citations`。
3. 解析前后 **Flask 进程内存**（RSS / Private）—— 这条我特别关心，docling 模型会留在进程里。
4. `_parse_lock` 的实际效果：两个并发提交时，第二个的 progress 是什么？总耗时是否≈两者之和？
5. 白名单改名的两处是否一致（贴出两个文件里的那一行），以及 `download_online` 确认没进白名单。
6. `git diff --stat` + 全仓库「20 个」出现的处数。

---

## 五、红线

- **只允许改**：`api_server.py`（新端点 + 白名单）、`services/review/task_manager.py`（白名单）、
  `mcp_server/search_server.py`、`mcp_server/selftest.py`、以及 B-5 列的文档。
- ❌ 不许改 `build_db/**`（解析器与写库逻辑）、`services/search/**`（检索与下载）、
  同步 `/api/papers/parse` 的行为、`tasks` 表结构。
- ❌ 不许引入新依赖（docling 已在，别加别的）。
- ❌ 不许 `git add -A`（仓库里有别人的 `_test_v3317b.py`）；提交前缀 `V33.17: 阶段六B 论文入库 —— `；
  **不要自己 push**。
- 🔴 **测试不许留垃圾数据**：真解析测试如果用副本，必须删掉新建的 `papers`/`paragraphs` 行与临时 PDF；
  汇报时要说明清理结果（`tasks` 表里的测试任务行可以留，那是正常的任务历史）。

---

## 六、一句话

这一条把「离线把手放进去」变成「模型自己能入库」——
但要把边界说清楚：**能入库、能查详情，不等于立刻能语义检索到**（Chroma 索引不在本单）。
