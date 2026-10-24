# 安装 SciPal MCP bundle —— 人工操作步骤

> 这份文件是给**你（用户）**在 DSH 里照着做的。
> CodeBuddy 不能代劳：`plugin_manager` 是 DSH 运行时内部工具，仓库侧（VS Code）调不到；
> 官方也明令禁止手写 profile 的 `package.json` / `cordis.patch.yml` 或用 shell 模拟安装。

---

## 步骤 0（一次性，必须在 DSH **完全退出**时做）

DSH 启动后会回写 profile patch，开着改会被覆盖。

1. **完全退出 DSH Desktop**（托盘 / 任务管理器确认 `DeepSeek Harness.exe` 已消失）
2. 备份并删除 `C:\Users\chenwei\.dsh\profiles\desktop\cordis.patch.yml` 中**手写**的
   `mcp-scipalhello` / `mcp-scipal` 两条 `insert` 条目。
   不删会因 `serverName` 重名，**加载直接报错**。

   > 本机实测：该文件共 108 行，两条冲突条目在 **第 65–76 行**和 **第 78–98 行**，
   > 整个 `- insert:` 块是 **第 64–98 行**（块内只有这两条，可整块删除）。
   > 第 0–4 条（`locale`、`agent-default-model`、`ui-settings-account`、`ui-chat`、`ui-settings`）**必须保留** ——
   > 其中 `ui-settings-account` 是账户引导状态，删了等于丢用户状态。

3. 用体检脚本确认已经清干净：

   ```powershell
   cd D:\sciPal
   .\venv_sciPal_py312\Scripts\python.exe scripts\precheck_dsh_bundle.py
   ```

   - **退出码 0** → 无冲突、bundle 合法，可以进入步骤 1
   - **退出码 1** → 还有 serverName 冲突，脚本会列出**具体行区间**，回去删
   - **退出码 2** → bundle 自身不合法，先别装，把输出发给 CodeBuddy

   脚本会自动把 profile 备份到 `tests/backups/cordis.patch.yml.<时间戳>.bak`（仓库内，git 之外唯一的安全副本）。

---

## 步骤 1（在 DSH 会话里，对模型说）

```
用 plugin_manager 执行 action: list_plugins 和 action: list_bundles，
报告当前已安装的插件与 bundle，特别是 MCP 相关条目。
```

目的：确认安装前基线，装完可对比。

---

## 步骤 2（在 DSH 会话里，对模型说）

```
用 plugin_manager 执行 action: install_bundle，
target 为 D:/sciPal/packages/dsh-scipal
```

> ⚠️ 如果它报 **pending build scripts**（待执行的构建脚本），**不要**点批准，
> **先停下来把报告发给我**。本 bundle 是配置型（零代码），正常不应有构建脚本。

---

## 步骤 3

**完全退出 DSH 再重启**。新装的包需要重启才加载新模块代。

---

## 步骤 4（验证）

在 DSH 会话里问模型：

```
你现在有哪些 mcp__ 开头的工具？
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
