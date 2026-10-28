# dsh-scipal — SciPal MCP 配置型 bundle

把 SciPal 的 MCP server 条目从「手写 profile patch」升级成**可单独安装/卸载的插件**。
零代码：只有 `package.json` / `cordis.patch.yml` / `locale/*.json` / `icon.svg`。

包含 **3 个 server 条目**（阶段五-B 按科研业务流拆分，见 `cordis.patch.yml` 注释）：

| id | serverName | 工具数 | 作用 |
|---|---|---|---|
| `mcp-scipalhello` | `scipalhello` | 1 | 零依赖哨兵（`ping`），用于区分故障在哪一侧 |
| `mcp-scipal-search` | `scipal-search` | 6 | 检索与下载：混合/在线检索、论文详情、启动下载、轮询进度 |
| `mcp-scipal-generate` | `scipal-generate` | 6 | 综述/大纲**只读 + 轮询**（不触发任何生成） |

> 旧的单进程条目 `mcp-scipal`（serverName `scipal`）已在阶段五-B 移除 —— 它的 5 个工具
> 与两个新 server 重复，白占模型上下文。`mcp_server/scipal_server.py` 仍保留作为**回退入口**。

---

## 🔴 安装 / 变更前必读：serverName 不能重名

官方 README 原文：

> **两条配置项使用相同的服务器名称时，后加载的一条会在加载时以明确错误失败。**

**本机现状（2026-10-24 19:40 起）**：bundle 已用 link 方式装进 `desktop` profile，
profile patch 已清场 —— **916 字节 / 5 条 `- id:` / 无 `insert` 块 / 无 `serverName`**，
因此**当前不存在重名冲突**，`scripts/precheck_dsh_bundle.py` 应返回 **退出码 0**。

以后若要再手写 MCP 条目，**先查重名再动手**：

```powershell
cd D:\sciPal
.\venv_sciPal_py312\Scripts\python.exe scripts/precheck_dsh_bundle.py
```

- 退出码 **0**：无冲突且 bundle 合法
- 退出码 **1**：有 serverName 冲突，脚本会给出 profile 里的**具体行区间**
- 退出码 **2**：bundle 自身不合法，先别装

### 还原（改坏了怎么办）

🔴 **不要用 `tests/cordis.patch.yml.bak` 整体还原。** 它只有 **297 字节**，内容仅为：

```yaml
- id: locale
  name: "@deepseek-ai/dsh-client-locale"
  config:
    preference: en
```

而当前 profile 是 **916 字节 / 5 条顶层条目**（bundle 装好后已清场，无 `insert`），
整体还原会一并抹掉：

| # | id | 会被抹掉的内容 |
|---|---|---|
| 0 | `locale` | `preference: en` |
| 1 | `agent-default-model` | 模型选择：`deepseek-account` / `deepseek-flash` / `reasoningEffort: high` |
| 2 | **`ui-settings-account`** | 🔴 **DSH 账户引导状态**：`step: done`、`purpose`、`process`、`completion: skipped`、`usage: compact`、`developerTools` |
| 3 | `ui-chat` | 界面偏好：`transcriptView: standard`、`performanceUsage: compact` |
| 4 | `ui-settings` | `enabled: false` |

第 2 条是**用户状态**（账户引导），不是可重建的配置 —— 丢了不会自动恢复。

**推荐做法**：不要整体还原。若只是 MCP 条目出问题，只处理 `insert` 块
（当前 profile 已无 `insert`，说明清场已完成）。行号一律以
`scripts/precheck_dsh_bundle.py` 的**实时扫描结果**为准，不要照抄文档里的旧行号。

**推荐的还原源：`tests/backups/`** —— 由体检脚本每次运行时生成的**完整快照**（含全部 6 条）：

```powershell
# 1) 看看有哪些备份
Get-ChildItem D:\sciPal\tests\backups\

# 2) 用其中一份还原（文件名换成实际的）
Copy-Item "D:\sciPal\tests\backups\cordis.patch.yml.20261024-174734.bak" "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml" -Force
```

`tests/cordis.patch.yml.bak`（297 B 基线）**仅当要彻底重置 profile**、且明确接受丢失账户状态时才用：

```powershell
Copy-Item "D:\sciPal\tests\cordis.patch.yml.bak" "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml" -Force
```

---

## 安装

> 逐步人工操作原文见 **[`INSTALL.md`](./INSTALL.md)**（含步骤 0 的清理与体检、pending build scripts 警告）。

安装动作由 **DSH 运行时**执行，本仓库的 CodeBuddy 没有 `plugin_manager`，无法代劳：

在 DSH 会话里让 agent 调用 `plugin_manager`，`action: install_bundle`，
`target` 填本目录的**绝对路径**：

```text
D:\sciPal\packages\dsh-scipal
```

或走 DSH Desktop 的插件安装 UI（若提供该入口）。

安装成功后重启 DSH，工具列表应出现 **35 个**（哨兵 1 + search 10 + generate 9 + guard 3 + data 12）：

```text
# 哨兵（1）
mcp__scipalhello__ping

# scipal-search（10）
mcp__scipal-search__health
mcp__scipal-search__search_hybrid
mcp__scipal-search__search_online
mcp__scipal-search__get_paper
mcp__scipal-search__download_online_papers
mcp__scipal-search__download_status
mcp__scipal-search__ask_question          ← 异步问答（>120s，轮询 review_task_status）
mcp__scipal-search__agentic_search        ← 异步多跳检索（轮询 review_task_status）
mcp__scipal-search__list_local_papers     ← 本地 PDF 与入库状态（精简视图）
mcp__scipal-search__parse_paper           ← 异步解析入库（立即返 task_id）

# scipal-generate（9：只读 + 轮询 + 两个异步 submit）
mcp__scipal-generate__health
mcp__scipal-generate__list_saved_outlines
mcp__scipal-generate__get_saved_outline
mcp__scipal-generate__get_review
mcp__scipal-generate__paper_citation_graph
mcp__scipal-generate__review_task_status
mcp__scipal-generate__generate_outline        ← 立即返 task_id，用 review_task_status 轮询
mcp__scipal-generate__cancel_review_task
mcp__scipal-generate__generate_review         ← 综述正文（分钟级，立即返 task_id）
```

## 变更 bundle 后的生效方式

本 bundle 是 **link 安装**（`~/.dsh/profiles/desktop/package.json` 里是
`"@local/dsh-scipal": "link:D:/sciPal/packages/dsh-scipal"`），所以：

| 动作 | 是否需要重装 | 是否必须重启 |
|---|---|---|
| 改 `cordis.patch.yml`（增删 server 条目） | ❌ 不需要 | ✅ **必须完全退出 DSH 再启动** |
| 改 `mcp_server/*.py`（工具实现） | ❌ 不需要 | ✅ 必须重启（新进程才加载新代码） |
| 改 `locale/*.json` / `icon.svg` | ❌ 不需要 | ✅ 重启后界面才更新 |

> 本机构型**没有 HMR**，profile 只在 DSH 启动时应用。改完文件不重启 = 没变。
> 重启后按上面的 **35 个**工具核对（旧的单进程 `scipal` server 已不再挂载，
> `selftest.py` 会额外跑它 5 个工具做回退覆盖，那是自检数不是挂载数）；少了哪个，先看该 server 的 `health` 工具，
> 再看 `python.exe` 进程数（3 条 server 命令 × 2 层进程 = 6 个）。

## 卸载

在 DSH 会话里让 agent 调用 `plugin_manager`（官方 `references/host-plugin.md:70`）：

```text
用 plugin_manager 执行 action: remove_bundle，
移除 @local/dsh-scipal（目录 D:/sciPal/packages/dsh-scipal）
```

卸载后：

- `~/.dsh/profiles/desktop/cordis.patch.yml` **不会**被删除，SciPal 仓库也不会被改动。
- 若想回到「手写配置」的老状态：把两条 MCP `insert` 重新加回 profile patch，
  或从 `tests/backups/cordis.patch.yml.<时间戳>.bak` 里抄回第 5 条（该备份含全部 6 条）。
- 🔴 **不要**用 297 B 的 `tests/cordis.patch.yml.bak` 整体覆盖 —— 会丢账户状态，详见上一节。
- 卸载后重启 DSH，`mcp__scipal*` 工具应消失。

---

## 前置条件

| 依赖 | 说明 |
|---|---|
| `D:/sciPal/venv_sciPal_py312/Scripts/python.exe` | 必须存在且装了 `mcp` 2.2.0（系统 Python 没装） |
| `D:/sciPal/tests/mcp_ping_server.py` | 哨兵脚本，零依赖 |
| `D:/sciPal/mcp_server/search_server.py` | `scipal-search` 脚本（薄转发 Flask） |
| `D:/sciPal/mcp_server/generate_server.py` | `scipal-generate` 脚本（只读 + 轮询） |
| `D:/sciPal/mcp_server/_forward.py` | 两个 server 共用的 HTTP 传输层 |
| SciPal Flask API | `http://127.0.0.1:5000` 需在运行；可用 `scripts/sciPal_watchdog.py` 常驻守护 |

> bundle 里的路径是**绝对路径**（`D:/sciPal/...`）。换机器或换目录时需要改 `cordis.patch.yml`。

---

## 文件

```text
packages/dsh-scipal/
├── package.json        # dsh.bundle.patch → ./cordis.patch.yml
├── cordis.patch.yml    # 三个 server 的 insert 条目（含三条铁律注释）
├── locale/en.json      # 英文展示名与描述
├── locale/zh.json      # 中文展示名与描述（用户语言）
├── icon.svg            # 原创图标（文献页 + 检索放大镜）
├── INSTALL.md          # 人工安装步骤（在 DSH 会话里逐字执行）
└── README.md           # 本文
```

### `cordis.patch.yml` 里保留的三条铁律

1. 新增条目必须包在 `insert:` 里；写成顶层 `- id: xxx` 会被判定为
   “targets that match no row” → warn 并跳过，且**不报错**（静默失败）。
2. `failOnStartupError`：**哨兵 `true`，两个业务 server `false`**。
   若业务 server 设 `true`，它启动失败会让整个 MCP client 拒绝激活，把哨兵也一起拖没，
   诊断能力归零。取 `false` 的代价是「失败不显式」——靠哨兵 + 各自 `health` 工具 + 进程计数兜。
3. 改配置要在 **DSH 关闭时**做；启动后 DSH 会回写该文件。

---

## 本目录未做的事

- 未写入 `~/.dsh/` 下任何文件
- 未执行 `install_bundle`
- 未修改 `mcp_server/`、`services/`、`api_server.py`
