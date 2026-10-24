# DSH 插件化路线图

> 制定：WorkBuddy　日期：2026-10-24　分支：`dev`
> 本文是**入口文档**。CodeBuddy 按 `CODEBUDDY.md` 清单读文档，看不到我们的对话，
> 所以下一步要干什么必须写在仓库里。
> 相关：`docs/DSH契约要点.md`（契约铁律）· `docs/DSH官方参考/`（18 份官方原文）·
> `docs/阶段五-服务器拆分与bundle化.md`（拆分的能力核对，本文直接引用不再重复）

---

## 0. 一句话现状

SciPal 已经能通过 MCP 被 DSH 调用（阶段三端到端通过，模型侧 6 个工具，真检索返回真实论文）。
**Python 业务代码零改动**——全部靠 `cordis.patch.yml` 的 `insert` + `mcp_server/` 薄转发。
剩下的工作是：把这条通路**正规化**（可安装卸载的 bundle）和**扩展**（按业务流拆 server）。

**根本约束**：DSH 是 TypeScript，SciPal 是 Python（157 py / 45k 行 / 425MB）。
**绝不 TS 重写核心逻辑**。一切跨语言都走 MCP stdio 桥，DSH 侧零 TS 代码。

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

冻结回滚线：**`freeze/v33.17`**（`a097397`），只许看不许改。

---

## 2. 下一步（按优先级）

### 🔴 2.1 【必须人做】bundle 实装验证

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

### 🔴 2.2 【必须人做】安装计划任务

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

### 🟢 2.3 【CodeBuddy】阶段五-B：拆 MCP server（按科研业务流）

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

### ✅ 2.4 【CodeBuddy】阶段四-B：小修 —— **已完成并验收**

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

### ✅ 2.5 文档治理 —— **已执行**（`f0beca4`）

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

## 2.0 📌 当前派单顺序（2026-10-24 更新）

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

## 3. ⚠️ 依赖顺序（别搞反）

**拆 server（2.3）会改变 bundle 的内容。** 建议顺序：

```
2.1 bundle 实装验证（先验证「能装能卸」这个机制本身）
        ↓ 确认能装
2.3 拆 MCP server → 同步更新 package/bundle 配置
        ↓
2.1 再装一次（验证拆分后仍可安装）
```

否则两个未知数叠一起，出问题分不清是 bundle 机制不通还是拆分改坏了。

2.2（装计划任务）和 2.4（小修）互相独立，可随时插队。

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
  用户不会被误导。**持久运行只能靠计划任务（2.2）。**
- 唯一失败的自检项：`abstracts.db: no such table: abstracts`（历史遗留，未触碰）。
- `self_check.py` 基线：通过 110 / 失败 1 / 总计 121。
