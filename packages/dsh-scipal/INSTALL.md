# 安装 SciPal MCP bundle —— 人工操作步骤

> 这份文件是给**你（用户）**在 DSH 里照着做的。
> AI 不能代劳：安装动作在 **DSH 桌面端的「插件」页**里完成，仓库侧（VS Code）碰不到那个界面；
> 官方也明令禁止手写 profile 的 `package.json` / `cordis.patch.yml` 或用 shell 模拟安装。
>
> **2026-10-24 已全程实测走通**（本机 `desktop` profile）：本地目录安装 → `Enable now` → 完全退出重启
> → 6 个 `mcp__` 工具全部可用。下面步骤按实测修订过，早期版本里「靠 `plugin_manager` 安装」
> 的说法**在本机走不通**，原因见步骤 0.5。

---

## 步骤 0（一次性，必须在 DSH **完全退出**时做）—— ✅ 本机已于 2026-10-24 18:22 完成

DSH 启动后会回写 profile patch，开着改会被覆盖。

**已完成的结果**：`~/.dsh/profiles/desktop/cordis.patch.yml` 现为 **916 B / 38 行 / 5 条 `- id:`**，
**没有 `insert:`、没有任何 `serverName`**（手写的 `mcp-scipal` / `mcp-scipalhello` 两条冲突条目已删）。
保留的 5 条：`locale` / `agent-default-model` / `ui-settings-account` / `ui-chat` / `ui-settings`。

> 历史记录（供需要重做的人参考）：清场前该文件 108 行，冲突的 `- insert:` 块在第 64–98 行，
> 内含 `mcp-scipalhello`（65–76）与 `mcp-scipal`（78–98）。**只删这个 insert 块及其手写注释**，
> 千万不要动 5 条 `- id:` —— 其中 `ui-settings-account` 是账户引导状态，删了等于丢用户状态。
> 另注：`tests/cordis.patch.yml.bak` 只有 297 B 基线（仅 `locale`），整体还原会抹掉账户状态。

若要复核是否仍然干净：

```powershell
cd D:\sciPal
.\venv_sciPal_py312\Scripts\python.exe scripts\precheck_dsh_bundle.py
```

- **退出码 0** → 无冲突、bundle 合法，可继续
- **退出码 1** → 还有 serverName 冲突，脚本会列出**具体行区间**
- **退出码 2** → bundle 自身不合法，先别装

脚本会自动把 profile 备份到 `tests/backups/cordis.patch.yml.<时间戳>.bak`。

---

## 步骤 0.5（2026-10-24 更正：**不要**去找 `plugin_manager`）

早期版本这里写的是「开启 Full access 后 `plugin_manager` 就会暴露」——**这条是错的，已作废。**

实测（`session_projcache` 会话缓存 + 实调用双重验证）：

| 观测 | 结果 |
|---|---|
| `permissions.preset` | `danger-full-access`（Full access **确实开了**） |
| `plugin_manager` 实调用 | 仍然 `Error: unknown tool` |
| `cordis_inspect_list` / `cordis_inspect_query` 实调用 | 同样 `unknown tool`（本机两个都没有） |

真实机制（来自随包文档 + 会话状态，二者一致）：

- 管理**服务** `@deepseek-ai/dsh-plugin-manager`（行 id `plugin-manager`）在 profile 里，所以**「插件」侧边栏可用**；
- 但暴露给 agent 的**工具**是另一个行：`tool-plugin-manager`（`@deepseek-ai/dsh-plugin-manager/tools`），
  **默认 `disabled: true`，只在「创造模式」(preset `cordis`) 启用**；本机会话是 `agentPreset: "standard"` → 对它不可见；
- Full access 只管沙箱与审批，**改不了预设禁用**。

**结论：安装不需要 `plugin_manager`，直接走步骤 2 的桌面插件页。**
只有想「让 `plugin_manager` 在标准模式常驻」时才需要折腾：在创造模式里做一个覆盖 `standard` 预设的 bundle
（把 `tool-plugin-manager` 加进该预设的 plugins）再装 —— 那属于另一个议题，与本 bundle 安装无关。

---

## 步骤 0.7（2026-10-24 实测补充：装 bundle 前先做「重启验伪」）

**为什么需要这一步**：步骤 0 是「完全退出后改盘上 patch」，但 DSH 是常驻进程，
**清场前的旧进程哪怕还在内存里，也会把旧 patch（含 `mcp-scipal` / `mcp-scipalhello`）继续挂成活跃 MCP**。
本机实测时间线：

```
18:22  清场（cordis.patch.yml → 916B / 5 行 / 无 MCP）
18:26  DSH 仍报「6 个 mcp__ 工具活跃」（旧进程，18:22 前就起了）
18:32  DeepSeek Harness.exe 全部重建 → 用清场后的 patch 重新 compose
```

也就是说：**不重启，你就分不清「这 6 个工具是旧配置残留」还是「bundle 已生效」**。
误判的后果 = 装 bundle 后 serverName 重名 → 加载直接报错。

**操作**（DSH 完全重启后、进会话的第一件事；不需要任何权限开关）：

```
列出你现在能用的所有以 mcp__ 开头的工具。没有就直说 0 个，不许从日志猜。
```

判读：

- **答 0 个** → 清场对运行态已生效，bundle 可以安全装（不会重名）。
- **仍答 6 个**（scipal 5 + scipalhello 1）→ 还有我们没找到的配置源
  （例如别的 patch overlay、`--patch` 传参、本机已装过的 bundle 残留、或 DSH_HOME 级配置）。
  **此时先停下来挖配置源，不要进步骤 2**，否则必然加载报错。

> 旁证：若模型答「没有 `plugin_manager`」，**不是权限问题，别再开 Full access 试**（见步骤 0.5：
> 它是 `tool-plugin-manager` 行在标准预设下被禁用，Full access 改不了这个）。

---

## 步骤 1（可选：装前基线）

不需要 `plugin_manager`。三条盘上事实就够做基线（在 DSH **完全退出**时看）：

```powershell
$p = "C:\Users\chenwei\.dsh\profiles\desktop"
Select-String -Path "$p\package.json" -Pattern "dsh-scipal"      # 装前应无输出
Get-ChildItem "$p\node_modules\@local" -ErrorAction SilentlyContinue  # 装前应不存在
(Get-Content "$p\cordis.patch.yml" | Select-String "^- id:").Count    # 应为 5
```

`cordis.patch.yml` **装完也仍然是 5 行**——bundle 的 `insert:` 两条 MCP 行由 bundle 层在启动时叠加，
不会写回 patch 层。所以别拿「patch 里没有 mcp 条目」当失败判据。

---

## 步骤 2（安装：桌面插件页 → 本地目录，2026-10-24 实测走通）

1. DSH 桌面 → 左侧 **插件** → **已安装**
2. 点 **添加插件**
3. 「包名或地址」填 **本地绝对路径**：

   ```
   D:/sciPal/packages/dsh-scipal
   ```

   会被识别为 **Local directory**（npm 包名 / GitHub 地址 / tarball 同样支持，
   只有「发现」标签页才是插件市场，与本地安装是两条独立通道）。
4. 确认安装。成功界面：**Installed** + `@local/dsh-scipal` + `Local directory` + `Version 1.0.0`
5. 点 **`Enable now`**

> ⚠️ 若报 **pending build scripts**（待执行的构建脚本），**不要点批准**，先停下来。
> 本 bundle 是配置型（零代码），正常不应有构建脚本。

装完的盘上三证（可自查）：

```
profiles/desktop/package.json          → dsh.profile.bundles 里出现 "@local/dsh-scipal"
                                         dependencies: "@local/dsh-scipal": "link:D:/sciPal/packages/dsh-scipal"
profiles/desktop/node_modules/@local/  → dsh-scipal -> /d/sciPal/packages/dsh-scipal  (symlink)
profiles/desktop/.plugin-manager/logs/operation-*/pnpm.log
                                       → "+ @local/dsh-scipal 1.0.0 <- D:\sciPal\packages\dsh-scipal"
```

symlink 意味着这是**链接安装**，改 bundle 里的文件即时生效，不必重装。

---

## 步骤 3（完全退出 DSH 再重启）

新装的包需要**完整重启**才加载新模块代（本机构型没有 HMR，profile 只在启动时应用）。
关窗口不算，要在任务管理器确认 `DeepSeek Harness.exe` 全部消失。

重启后**先看进程层证据**（比问模型可靠，模型会拿旧日志拼清单）：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'mcp_' } |
  Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```

应看到 **2 个** stdio 服务，且 `ParentProcessId` 指向 `DeepSeek Harness.exe`：

```
... python.exe D:/sciPal/mcp_server/scipal_server.py     ← scipal
... python.exe D:/sciPal/tests/mcp_ping_server.py        ← scipalhello 哨兵
```

（本机实测时间戳：DSH 19:45 启动 → 19:46:16 拉起这两个子进程。**这两个进程不存在 = bundle 没生效**，
此时不管模型说什么都算失败。）

---

## 步骤 4（验证）

> ⚠️ **前置**：`scipal` 这 5 个工具依赖 SciPal Flask（端口 5000）。
> 验证前确认它在跑（见 2.2：装计划任务，或临时 `python api_server.py`）。
> Flask 没起时 `scipal` 会失败而哨兵仍在 —— 别误判成配置问题。

**问模型要工具清单**（`cordis_inspect_*` 在本机不存在，只能用这一路）：

```
列出你现在能用的所有以 mcp__ 开头的工具，逐个列名字。
不许从日志猜；没有就直说 0 个。列完对每个工具真实调用一次并贴出返回。
```

期望看到 **6 个**：

```text
mcp__scipalhello__ping                                   ← 哨兵（零依赖）
mcp__scipal__health
mcp__scipal__search_papers
mcp__scipal__get_paper
mcp__scipal__get_abstract
mcp__scipal__task_status
```

**判读要点**：

- 工具**存在但返回业务错误**（如 `Paper not found` / `task not found` / 404）→ **正常**，
  说明已注册且链路通，只是参数不存在；**只有 `unknown tool` 才算没挂上**。
- `health` 应返回 `status: ok` + `db_exists: true`；`ping` 应返回 `{"ok": true}`。这两个零依赖，
  任何时候都能用来判定 MCP 通道是否健康。

**哨兵诊断矩阵**（出问题先看这个）：

| 现象 | 结论 |
|---|---|
| 哨兵出现 + 真实出现 | 全通 |
| 哨兵出现 + 真实消失 | SciPal 侧问题（脚本 / Flask / 超时） |
| 哨兵消失 + 真实消失 | DSH 侧或配置层问题（insert 写法 / 环境清洗 / 启动失败） |

---

## 出问题怎么退回去

见 `README.md` 的「还原（改坏了怎么办）」一节。

**不要**整体还原 `tests/cordis.patch.yml.bak` —— 那只有 297 字节，会抹掉账户状态与界面偏好。
优先用 `tests/backups/` 里带时间戳的最新备份。
