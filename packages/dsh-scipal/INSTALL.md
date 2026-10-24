# 安装 SciPal MCP bundle —— 人工操作步骤

> 这份文件是给**你（用户）**在 DSH 里照着做的。
> AI 不能代劳：安装动作在 **DSH 桌面端的「插件」页**里完成，仓库侧（VS Code）碰不到那个界面；
> 官方也明令禁止手写 profile 的 `package.json` / `cordis.patch.yml` 或用 shell 模拟安装。
>
> **2026-10-24 已全程实测走通**（本机 `desktop` profile）：桌面插件页填本地目录 → `Installed` →
> `Enable now` → 完全退出重启 → 工具全部可用。步骤 1/2 就是这条唯一走通的路径；
> 早期版本里「靠 `plugin_manager` 安装」的说法**在本机走不通**，原因见步骤 0.5。

---

## 步骤 0（仅在 profile 里还有手写 MCP 条目时需要）

**本机现状（2026-10-24 19:40 起）已清场**：profile patch 为 **916 字节 / 5 条 `- id:`**，
无 `insert`、无 `serverName`，bundle 已 link 安装 → **跳过本步，直接去步骤 3（重启）**。

换机器或重装时需要重来时：

1. **完全退出 DSH Desktop**（托盘 / 任务管理器确认 `DeepSeek Harness.exe` 已消失）——
   DSH 启动后会回写 profile patch，开着改会被覆盖
2. 打开 `C:\Users\<用户名>\.dsh\profiles\desktop\cordis.patch.yml`，删除**手写**的
   `mcp-scipalhello` / `mcp-scipal-*` 的 `- insert:` 块。不删会因 `serverName` 重名，
   **加载直接报错**。
   第 0–4 条（`locale`、`agent-default-model`、`ui-settings-account`、`ui-chat`、`ui-settings`）
   **必须保留** —— 其中 `ui-settings-account` 是账户引导状态，删了等于丢用户状态。
3. 用体检脚本确认已经清干净：

   ```powershell
   cd D:\sciPal
   .\venv_sciPal_py312\Scripts\python.exe scripts/precheck_dsh_bundle.py
   ```

   - **退出码 0** → 无冲突、bundle 合法，可以继续
   - **退出码 1** → 还有 serverName 冲突，脚本会列出**具体行区间**，回去删
   - **退出码 2** → bundle 自身不合法，先别装，把输出发给 CodeBuddy

   脚本会自动把 profile 备份到 `tests/backups/cordis.patch.yml.<时间戳>.bak`（仓库内，git 之外唯一的安全副本）。

---

## 步骤 0.5（🔴 不要去找 `plugin_manager`，2026-10-24 实测作废该路线）

早期版本这里写的是「开启 Full access 后 `plugin_manager` 就可用」——**错的，已删除。**

实测（会话缓存 `session_projcache` + 真实调用双重验证）：

| 观测 | 结果 |
|---|---|
| `permissions.preset` | `danger-full-access`（Full access **确实开了**） |
| `plugin_manager` 实调用 | 仍然 `Error: unknown tool` |
| `cordis_inspect_list` / `cordis_inspect_query` 实调用 | 同样 `unknown tool`（本机两个都没有） |

真实机制：

- 管理**服务** `@deepseek-ai/dsh-plugin-manager`（行 id `plugin-manager`）在 profile 里 → **「插件」侧边栏可用**；
- 但暴露给 agent 的**工具**是另一行 `tool-plugin-manager`（`@deepseek-ai/dsh-plugin-manager/tools`），
  **默认 `disabled: true`，只在「创造模式」(preset `cordis`) 启用**；本机会话是 `agentPreset: "standard"` → 不可见；
- Full access 只管沙箱与审批，**改不了预设禁用**。

**结论：安装不需要 `plugin_manager`，走步骤 1 的桌面插件页。**
`list_plugins` / `install_bundle` 那一套在本机拿不到，不要再试。

---

## 步骤 0.7（装之前先做「重启验伪」）

DSH 是常驻进程，**清场前的旧实例会继续把旧 patch 挂成活跃 MCP**。本机实测时间线：

```
18:22  清场（cordis.patch.yml → 916 B / 5 行 / 无 MCP）
18:26  DSH 仍报「6 个 mcp__ 工具活跃」   ← 旧进程，18:22 前就起了
18:32  DeepSeek Harness.exe 全部重建 → 用清场后的 patch 重新 compose
```

不重启就分不清「这 6 个工具是旧配置残留」还是「新配置已生效」。所以**完全重启后、装/改之前先问**：

```
列出你现在能用的所有以 mcp__ 开头的工具。没有就直说 0 个，不许从日志猜。
```

- 答 **0 个** → 运行态已跟上磁盘，可以继续（改 bundle 前的基础状态就是 0）；
- 若仍报一堆旧工具 → 还有未知配置源，**先停下来挖**，别改 patch。

> 判据补充：模型说「没有 `plugin_manager`」时**不是权限问题**（见步骤 0.5），别再开 Full access 试。

---

## 步骤 1（安装：桌面插件页 → 本地目录，唯一走通的方式）

本机**已完成过**（link 安装）。仅换机器/重装时需要：

1. DSH 桌面 → 左侧 **插件** → **已安装** → **添加插件**
2. 「包名或地址」填 **本地绝对路径**：

   ```
   D:/sciPal/packages/dsh-scipal
   ```

   会被识别为 **Local directory**（npm 包名 / GitHub 地址 / tarball 同样支持；
   只有「发现」标签页才是插件市场，与本地安装是两条独立通道）。
3. 确认 → 成功界面为 **Installed** + `@local/dsh-scipal` + `Local directory` + `Version 1.0.0`

装成的盘上三证（可自查）：

```
profiles/desktop/package.json          → dsh.profile.bundles 含 "@local/dsh-scipal"，
                                         dependencies 为 "link:D:/sciPal/packages/dsh-scipal"
profiles/desktop/node_modules/@local/  → dsh-scipal -> /d/sciPal/packages/dsh-scipal（symlink）
profiles/desktop/.plugin-manager/logs/operation-*/pnpm.log
                                       → "+ @local/dsh-scipal 1.0.0 <- D:\sciPal\packages\dsh-scipal"
```

---

## 步骤 2（点 `Enable now`）

安装完成后在界面上点 **`Enable now`**，启用这一层。

> ⚠️ 若安装时它报 **pending build scripts**（待执行的构建脚本），**不要**点批准，
> 先停下来报告。本 bundle 是配置型（零代码），正常不应有构建脚本。

> 因为 bundle 是 **link 安装**，之后**改包内文件（`cordis.patch.yml` / `mcp_server/*.py`）不需要重装**，
> 但每次都必须完全重启才生效（见步骤 3）。

---

## 步骤 3

**完全退出 DSH 再重启**。新装的包 / 改过的 patch 只在启动时应用（本机构型无 HMR）。

---

## 步骤 4（验证）

### 4.1 工具清单

在 DSH 会话里问模型：

```
你现在有哪些 mcp__ 开头的工具？
```

期望看到 **16 个**（哨兵 1 + search 6 + generate 9）：

```text
mcp__scipalhello__ping                                   ← 哨兵（零依赖）

mcp__scipal-search__health
mcp__scipal-search__search_hybrid
mcp__scipal-search__search_online
mcp__scipal-search__get_paper
mcp__scipal-search__download_online_papers
mcp__scipal-search__download_status

mcp__scipal-generate__health
mcp__scipal-generate__list_saved_outlines
mcp__scipal-generate__get_saved_outline
mcp__scipal-generate__get_review
mcp__scipal-generate__paper_citation_graph
mcp__scipal-generate__review_task_status
mcp__scipal-generate__generate_outline
mcp__scipal-generate__cancel_review_task
mcp__scipal-generate__generate_review
```

> **为什么是 16 而不是 20**：旧的单进程 `scipal` server（5 个工具）已经不再挂载，
> `mcp_server/scipal_server.py` 只作为回退入口留在仓库里。`selftest.py` 会跑 3 个文件、
> 断言 **23 项**（含 legacy 的 5 个工具），**那是自检覆盖，不是挂载数**——别拿它当期望值。

### 4.2 进程数硬判据

新 server 挂载成功的**硬判据**：命令行含 `mcp_` 的 `python.exe` 进程总数 **从 4 变成 6**。

原因：每条 server 命令都会出**两层进程**（venv 启动器 + 它 fork 的系统 python）：

| 阶段 | 命令数 | 进程数 |
|---|---|---|
| 拆分前（哨兵 + 单 server） | 2 | 4 |
| 拆分后（哨兵 + search + generate） | 3 | **6** |

父进程链最终都指向 `DeepSeek Harness.exe`。数不到 6 个，说明有 server 没起来。

### 4.3 分层诊断

| 现象 | 结论 |
|---|---|
| 哨兵 + 两个 `health` 都在 | 全通 |
| 哨兵在，某个 server 的 `health` 报连不上 | 该 server 或 Flask 侧问题（先看 Flask 是否在跑） |
| 哨兵在，某个 server 整个消失 | 该 server 脚本启动失败（看 `failOnStartupError: false` 导致不显式） |
| 哨兵也不在 | DSH 侧或配置层问题（insert 写法 / 环境清洗 / 启动失败） |

---

## 出问题怎么退回去

见 `README.md` 的「还原（改坏了怎么办）」一节。

**不要**整体还原 `tests/cordis.patch.yml.bak`（297 B）—— 会抹掉账户状态与界面偏好。
优先用 `tests/backups/` 里带时间戳的最新备份。
