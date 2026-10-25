# DSH 插件化路线图

> 制定：WorkBuddy　日期：2026-10-24　分支：`dev`
> 本文是**入口文档**。CodeBuddy 按 `CODEBUDDY.md` 清单读文档，看不到我们的对话，
> 所以下一步要干什么必须写在仓库里。
> 相关：`docs/DSH契约要点.md`（契约铁律）· `docs/DSH官方参考/`（18 份官方原文）·
> `docs/阶段五-服务器拆分与bundle化.md`（拆分的能力核对，本文直接引用不再重复）

---

## 0. 一句话现状（2026-10-25 11:30 更新）

**阶段五已全部收口**：SciPal 通过 MCP 以 **3 个 stdio server / 18 个工具**接入 DSH Desktop，
bundle `@local/dsh-scipal` 已实装（link 安装），Flask 由计划任务 `SciPalWatchdog` 托管，
**业务代码改动仅限异步端点与检索器注入**（见 §2），其余全部是 `mcp_server/` 薄转发。

| server | 工具数 | 内容 |
|---|---|---|
| `scipalhello` | 1 | 零依赖哨兵 `ping` |
| `scipal-search` | 8 | health / 检索（本地·在线·混合）/ 论文详情 / 在线下载+轮询 / **问答** / **多跳检索** |
| `scipal-generate` | 9 | health / 大纲（读·列表·**生成**）/ 综述详情 / 引用图谱 / 任务状态 / **取消** / **综述生成** |

**根本约束不变**：DSH 是 TS，SciPal 是 Python（157 py / 45k 行 / 425MB），**绝不 TS 重写**，
一切跨语言走 MCP stdio 桥，DSH 侧零 TS 代码。

---

## 1. 已完成

| 阶段 | 内容 | 提交 |
|---|---|---|
| 零 | DSH 环境探明（profile=desktop、无 MCP 配置 UI、`dsh-mcp-client` 在 app.asar） | `319c6de` `a1ede56` |
| 一 | 静态架构骨架扫描（3,922 节点 / 12,818 边 / 70 条 HTTP 路由） | `10c8d9b` |
| 三 | MCP 端到端打通，5 个只读工具 + 1 个哨兵 | `a584763` `63b50c0` `6c67f4d` |
| 四 | 服务常驻方案（消除手动起 Flask） | `1c5a1cd` |
| 四-A | watchdog + 自启脚本 + 工具侧提示 | `f017b54` |
| 四-A 修订 | 修验收发现的 4 项缺陷 | `f9197b5` |
| 四-A 验收 | 两轮验收报告 | `549af80` `3f4a471` |
| 五-A | 配置型 bundle `packages/dsh-scipal`（零代码） | `2457e85` |
| 五-A 实装 | 桌面端「本地目录」安装 + `Enable now` + 完全重启，6 工具全通（进程层复核） | 见 `packages/dsh-scipal/INSTALL.md` |
| 五-B | 拆 `scipal-search` / `scipal-generate`，删旧单进程 `scipal`（13 工具） | `b263961` `5c53bd3` |
| 五-C C-1 | 大纲生成异步接入（`generate_outline` / `cancel_review_task`，15 工具） | `24ee394` |
| 五-C C-2 | 综述生成异步化 + 私有 `ReviewGenerator` 隔离 + `threaded=True`（16 工具） | `5b03055` |
| 看门狗修复 | 拉起后等就绪、拉起前判端口、`--status`；消除实例堆积（曾滚到 8 个） | `ca21a5a` |
| 五-C C-3 | 问答 / 多跳检索异步接入；**先修检索栈重复加载（71.5 s → 1.2 s）**（18 工具） | `62e1c03` |
| 五-C 收尾 | selftest 清理改走 HTTP、失败可见、遗留任务检查 | `e7c63c0` |

冻结回滚线：**`freeze/v33.17`**（`a097397`），只许看不许改。

---

## 2. 阶段五完成情况（2026-10-25 收口）

### 2.1 业务代码改了什么（这是唯一非薄转发的部分）

| 改动 | 位置 | 为什么 |
|---|---|---|
| `POST /api/review/generate_async` | `api_server.py` | 综述生成分钟级、超 MCP 60 s；**线程内 new 私有 `ReviewGenerator`**（共享单例的 `use_llm_verification` / `_last_draft` 会串台） |
| `POST /api/qa/ask_async` | `api_server.py` | 问答实测 >120 s |
| `POST /api/agentic/search_async` | `api_server.py` | 多跳实测 71.5 s（1 跳） |
| `_review_generate_lock` | `api_server.py` | `threaded=True` 后同步路由串行化，保护共享单例 |
| `threaded=False → True` | `api_server.py` 末尾 | 单线程 server 会被一次同步重请求堵死全站 |
| `QAService(retriever=...)` | `services/qa/qa_service.py` | 不再自建检索栈（`UnifiedRetriever` 是饿汉式，重复加载模型） |
| `AgenticSearcher(retriever=get_retriever())` | `api_server.py` | 此前**每次请求**重建检索栈 |

### 2.2 三条实测结论（都已写进 `mcp_server/README.md`，别再反推）

1. **「异步会饿死请求循环」是错的** —— 21.8 s 是 embedding/reranker **冷加载一次性**；
   模型热之后任务 5–7 s 跑完，同期 35 次 health 采样全在 0.006–0.039 s。
2. **真正的瓶颈是 `threaded=False`**（单线程 server）+ **共享单例的可写状态**，两者都已在 C-2 修掉。
3. **重复加载检索栈代价极大**：`/api/agentic/search` 由 71.5 s → **热态 1.2 s（约 58 倍）**，
   连续 4 次 RSS 仅 +3.9 MB。**首次仍 109 s（冷加载）**，所以异步端点必须保留。

### 2.3 工具数上限的取舍

原则是 **≤8 工具/server**（约束是模型上下文与选择准确率，不是显存 ——
MCP 进程不加载模型，实测单个 ≈65–70 MB）。两次破例都在 `scipal-generate`（9 个）：
`generate_outline` / `generate_review` 与同 server 的「读结果」工具属于同一个工作流闭环，
拆第四个 server 要多一个常驻进程，换不来收益。

### 2.4 尚未派单的事项（都不是阶段五的阻塞项）

| 事项 | 判断 | 备注 |
|---|---|---|
| `POST /api/papers/parse` 挂进 MCP | **已排入阶段六-B** | ⚠️ 更正：`parse` 收的是 JSON `filename`（**不是** multipart，multipart 的是 `import`）；真问题是 docling 解析耗时未知，需异步 |
| `scipal-guard` 独立 server | **阶段六-C，待决策** | 卡在「词表从哪来」（统计生成 / 用户提供 / MeSH），不是卡在代码；无词表就只是重复 QA 已有的 `validation` |
| 同步路由下线（`review/generate`、`qa/ask`、`agentic/search`） | **不下线** | 前端仍在用；async 是**新增**不是替换 |
| 看门狗日志落盘 | **已完成** | `logs/sciPal_watchdog.log`（stdout 双写 + RUN MARKER + 5 MB 轮转）；状态切换日志带 `listening pids/count`，`count > 1` 额外打 `⚠️ 检测到多实例监听` |
| `review` 任务跨重启丢失 | **已排入阶段六-A（本轮派单）** | `services/review/task_manager.py` 是进程内内存 dict → 改成 SQLite `tasks` 表（表已存在、0 行、11 列），保留 9 方法签名与 7 键返回 |

→ **阶段六的分阶段规划与派单顺序见 `docs/阶段六-规划与派单.md`**（6-A 任务持久化 → 6-B 论文入库 → 6-C guard）。

---

## 2.9 历史留档：阶段五派单前的原始步骤（**已全部完成，勿照做**）

> 以下为 2026-10-24 的状态记录，保留是因为里面有踩坑细节（如清场行号、`plugin_manager` 的结论）。
> **当前有效流程请看 `packages/dsh-scipal/INSTALL.md`**。

### 🔴 2.9.1 bundle 实装验证

**为什么必须人做**：DSH Desktop 无 MCP 配置 UI，CLI 管不了 `desktop` profile，
agent 无法自助验证「工具是否出现在模型工具列表」。

**这是阶段五-A 的真正验收**——「可安装/可卸载」这个目标，只有装上才知道成不成立。

> 📋 配套：`docs/工单-bundle收尾.md`（CodeBuddy 侧：补 zh locale、写只读 precheck 脚本、
> 写 INSTALL.md 四步原文、README 补卸载章节）。

**官方唯一认可的安装方式是 DSH 会话内调 `plugin_manager` `action: install_bundle`**，
官方明令**禁止**手写 profile 的 `package.json` / `cordis.patch.yml`（`SKILL.md:8,10`）。
所以步骤 3 的「删手写条目」是**清场**（避免重名），不是安装动作本身。

> **✅ 步骤 0（清场）已于 2026-10-24 18:22 完成**（提交 `d814af7`）：
> profile `cordis.patch.yml` 由 107 行 → **38 行**，删除了
> **第 4–20 行**（手写 v3 注释头）与 **第 56–107 行**（SciPal MCP 段，含两条 insert）；
> 保留了第 1–3 行（DSH 官方模板注释）与第 21–55 行 5 条原始配置
> （**`ui-settings-account` 账户状态完好**：`step: done` / `purpose: null` / `process: standard`）。
> 体检脚本退出码 **由 1 变为 0**。
> 清场前后两份基线已入库：`...182049.bak`（4209B，清场前）/ `...182218.bak`（916B，清场后）。
>
> **剩余步骤 1–4 需你在 DSH 会话内完成**（`plugin_manager` 是运行时内部工具，仓库侧调不到）。

步骤：
1. **完全退出 DSH**（开着改配置会被退出时的状态写回覆盖）。
   脚本自己也会检测并警告「DSH 正在运行」。
2. 备份 `~/.dsh/profiles/desktop/cordis.patch.yml`（仓库外，git 救不回来）。
   建议用 E-2 交付的 `scripts/precheck_dsh_bundle.py`（会存到仓库内的 `tests/backups/`）。
3. **只删掉手写的 `mcp-scipalhello` / `mcp-scipal` 两条 `insert`**
   —— 🔴 **不删会重名冲突，加载直接报错**（官方明示：两个配置用同一 server name，后者加载失败）。
   🔴 **不要整体还原 `tests/cordis.patch.yml.bak`**（只有 297B 的阶段零基线）。
   当前文件是 4209B / 6 条：locale、agent-default-model、
   **ui-settings-account（账户状态）**、ui-chat、ui-settings、insert(两条 MCP)。
   整体还原会**连 DSH 账户状态和界面偏好一起抹掉** —— 只删最后那个 `insert` 块即可。
4. 安装 bundle：在 DSH 会话里让 agent 调 `plugin_manager` `action: install_bundle`，
   `target` = `D:\sciPal\packages\dsh-scipal`（这是官方唯一认可的方式，见 §2.1 开头）。
5. **完全退出再重启 DSH**（重载会复用旧子进程）。
6. 验证：新会话问模型「你有哪些 `mcp__` 工具」，应出现
   `mcp__scipalhello__ping` + `mcp__scipal__{health,search_papers,get_paper,get_abstract,task_status}`。

若失败，用哨兵定位（这是当初同时挂两个 server 的目的）：
- 哨兵在 + 真实在 → 全通
- 哨兵在 + 真实不在 → SciPal 侧（脚本 / Flask / 超时）
- 哨兵不在 → DSH 侧或配置层（insert 写法 / 环境清洗 / 启动失败）

---

### ✅ 2.9.2 安装计划任务 —— **已安装并验收（2026-10-25）**

装上才真正消除「手动起 Flask」：

```powershell
powershell -File D:\sciPal\scripts\install_autostart.ps1
```

装完回读确认：

```powershell
Get-ScheduledTask -TaskName SciPalWatchdog | Select-Object -ExpandProperty Principal | Select-Object RunLevel
Get-ScheduledTask -TaskName SciPalWatchdog | Select-Object -ExpandProperty Settings | Select-Object ExecutionTimeLimit
```

期望：`RunLevel = Limited`、`ExecutionTimeLimit = PT0S`（无限，无 3 天强制终止）。

---

### ✅ 2.9.3 阶段五-B：拆 MCP server —— **已完成（2026-10-25，实际结果见 §2）**

目标：`scipal-search` / `scipal-generate` 两个 server。

**详细能力核对见 `docs/阶段五-服务器拆分与bundle化.md`，本文不重复。** 关键结论与硬约束：

- `scipal-search`：文献下载、解析、入库、检索 —— **完全可行，零新增路由**
- `scipal-generate`：多轮渐进式提问、综述生成、引用追踪 —— ⚠️ 可行但有硬约束
- `scipal-guard`：防幻觉约束、领域词表校验 —— **暂缓独立**（领域词表校验能力不存在）。
  防幻觉结论先作为 `generate` 的一个工具暴露（读 `/api/qa/ask` 的 `validation` 字段）

🔴 **硬约束（MCP 60 秒上限）**：所有长任务工具必须
**「立即返回 job 句柄 + 独立 status 工具轮询」**，严禁同步等待。
SciPal 已有轮询基础设施：`/api/tasks/<id>`、`/api/review/task/<id>`、`/api/search/download_status`。

其他必须遵守：
- 新 server 一律**薄转发**（只用 `urllib` 打本地 Flask），**禁止 `from services...` import**
  —— 否则子进程会加载模型（单 server ≈68MB vs Flask ≈1123MB，模型必须留在 Flask 里共享）
- `serverName` 限 `[A-Za-z0-9_-]{1,32}`；工具公开名 `mcp__<serverName>__<rawName>`
- stdio 子进程环境被清洗（删 `/KEY|PASSWORD|SECRET|TOKEN/i` 全部变量 + 所有 `DSH_*`）
  → 密钥必须在 `env:` 显式重填，`no_proxy` 也要显式写（本机有 `http_proxy`）
- 每加一个 server，`packages/dsh-scipal/cordis.patch.yml` 要同步加 `insert` 条目

---

### ✅ 2.9.4 【CodeBuddy】阶段四-B：小修 —— **已完成并验收**

- 版本指针已统一为 V33.17，历史注释保留；`run_db_migrations()` 已补 `import sqlite3`。
- 验收：`/api/health` → `V33.17`，banner → `Sci-Pal API V33.17`，`self_check.py` 110/1/121 无回归。
- **工单 C 已完成**（`2f6607f`）：C-0 误导文案已修、C-1 确认废弃、C-2 版本守卫已加（自检 111/1/122）。
- **✅ `app.py` 已于 2026-10-24 删除**（`f0beca4`）：用户点头后执行，六处入口文档措辞同步改为「已删除」。
  `routes/` 暂保留（待单独确认），**`config/settings.py` 绝不能删**
  —— 它另被 `build_db/db_writer.py`（`api_server.py` 引 6 处）与 `database/init_db.py` 引用。

> 📋 **`docs/工单-C-app-py入口.md`**（已完成）—— 含端口冲突 / 路由缺失 / 孤儿 blueprint 三条硬证据。

1. **版本指针三处统一**：`api_server.py:172`（`/api/health` 返回 `V25.14`）、
   `api_server.py:2035`（banner `V25.17`）、`VERSION`（`V33.17`）
   → 统一为 V33.17，**保留所有 `# V25.xx` 历史注释**。
2. **补 `import sqlite3`**：`run_db_migrations()`（`api_server.py:1963` 处直接 `sqlite3.connect`）缺导入，
   日志实证 `⚠️ 数据库迁移跳过（不影响运行）: name 'sqlite3' is not defined` —— 迁移长期没跑。
3. 建议：给版本指针加个守卫，别再靠手改。

---

### ✅ 2.9.5 文档治理 —— **已执行**（`f0beca4`）

> 📋 **清单见 [`docs/文档治理-清单.md`](./文档治理-清单.md)**（判定依据与引用统计）。

已执行（用户 2026-10-24 点头）：

| 动作 | 对象 |
|---|---|
| 删除（与另一份同字节） | `docs/README-WINDOWS.md`、`docs/WINDOWS-INSTALL-GUIDE.md`、`docs/WORKLOG.md`、`docs/接口.md` |
| `git mv` 改名 | 怪名 P2 文件 → `docs/P2-优先级分类与架构图索引.md` |
| 标「历史快照」 | `docs/ARCHITECTURE.md`（根版是超集，多 V33.14 NLI 章节 13 行） |
| 版本同步 | `docs/README.md` V33.13 → V33.17 |
| 补约定 | `docs/协作约定.md` §3.1 文档落位 |

- **两份都保留**：`README.md`（根正文 vs docs 索引页）、`docs/架构.md` 与 `docs/架构总览.md`（详版 vs 摘要，均在阅读清单）
- ⚠️ **更正**：`AGENTS.md` / `WORK_LOG.md` / `AI_CONTEXT.md` / `CODEBUDDY.md` **只在根目录，无副本**，不要动
- 遗留：`api_server.py:2` docstring 写 `V25.8`（守卫故意不覆盖，是文档说明不是运行时指针）

---

## 2.95 历史留档：2026-10-24 派单顺序（**三张工单已全部完成**）

三张工单**互不依赖，可以并行**；但按「链路靠前的先做」排优先级：

| 优先级 | 工单 | 文件 | 为什么 |
|---|---|---|---|
| **P0** | bundle 收尾 E-1 ~ E-5 | `docs/工单-bundle收尾.md` | 卡着 2.1 实装（人等脚本才能安全清场） |
| **P1** | 工单 C（`app.py` 入口处置） | `docs/工单-C-app-py入口.md` | 独立；含一条真会坑人的误导文案 |
| **P2** | 文档治理 | `docs/工单-文档治理.md` | 独立；只出清单不执行删除 |

> ⚠️ **派单时必须显式写「本工单现在就执行」**。
> 2026-10-24 踩过：CodeBuddy 看到工单文件是新出现的未跟踪文件，当成「下一轮」，
> 转而把自己早先的提交 `2457e85` 报成本次成果 → 白等一轮。
> 可见 `docs/阶段五A-验收报告.md` 第三节。

---

## 3. ✅ 依赖顺序（已走完，留档）

阶段五实际执行顺序与下面这条建议**一致**，所以没有再出现「分不清是 bundle 机制不通还是拆分改坏了」的情况：

```
2.1 bundle 实装验证（先验证「能装能卸」这个机制本身）   ✅ 已装并验通 6 工具
        ↓
2.3 拆 MCP server → 同步更新 package/bundle 配置        ✅ 3 server / 13 工具
        ↓
重启验证拆分后仍可挂载                                  ✅ 旧名消失 + 旧进程为 0
        ↓
五-C（C-1 大纲 / C-2 综述 / C-3 问答+多跳）             ✅ 18 工具
```

2.2（计划任务）✅ 已装；2.4（小修）✅ 已完成。

> **下次再动 server 结构时，仍然照这个顺序走**：先确认机制，再改内容，最后复验。

---

## 4. 已结案的旧待办

- ~~「master 独有资产合进 dev」~~ —— 2026-10-24 核实：`git diff --stat dev..master`
  207 文件 / +48152 / -5516，但排除废弃的 `sci-pal-scaffold/` 后，master 独有只剩
  LICENSE（疑似行尾差异）、ARCHITECTURE 版本号、CODEBUDDY.md 两行和一堆 HTML 副本。
  **没有要往回合的资产，本条关闭。**
- ~~玄木阶段四（V4 Pro 逐块重写）/ 阶段五（Qwen 核对 inject）~~
  —— 走 MCP 路线不写插件代码，inject 风险归零，已取消。

---

## 5. 已知限制（记录在案，不再修）

- **`--once` 拉起的服务会随终端退出被回收**。已加 `CREATE_BREAKAWAY_FROM_JOB`
  （实测 `breakaway=已启用`，未降级）但**无效**——该标志只脱离 Job Object，**不改变父子进程链**，
  宿主按后代进程树清理时仍会被杀。已实测两次确认。
  → 代码与文案四处（docstring / epilogue / 工具错误文案 / `--help`）均已显式声明，
  用户不会被误导。**持久运行只能靠计划任务（见 §2.9.2，已于 2026-10-25 安装并验收）。**
- **看门狗日志已落盘**：`logs/sciPal_watchdog.log`（stdout 双写，5 MB 轮转保留 2 份）。
  每次启动写 RUN MARKER（含脚本 `mtime/size`，可直接判断跑的是不是修好的那版）；
  状态切换日志带 `listening pids/count`，`count > 1` 会额外打 `⚠️ 检测到多实例监听`。
  写失败（磁盘满/权限/目录被删）只提示一次后静默走 stdout，不影响守护运行。
- 唯一失败的自检项：`abstracts.db: no such table: abstracts`（历史遗留，未触碰）。
- `self_check.py` 基线：通过 111 / 失败 1 / 总计 122。
