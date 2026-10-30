# 阶段五-A 验收报告

> 验收方：WorkBuddy　被验收：CodeBuddy 提交 `2457e85`
> 验收时间：2026-10-24 17:35-17:45　分支：`dev`
> 工单：`docs/工单-bundle收尾.md`

---

## 一、结论速览

| 项 | 结论 |
|---|---|
| **A · bundle 本体（`packages/dsh-scipal`，`2457e85`）** | ✅ **通过**（我独立复核，不依赖对方脚本） |
| **B · 收尾工单 E-1 ~ E-4** | ❌ **未执行** —— CodeBuddy 把工单误判为「下一轮工单」，只复核了本体 |
| **C · 新发现的风险（README 还原命令）** | 🔴 **需修**，见第四节 |

**一句话**：bundle 包本身做对了，但「让它能被正式安装」这个收尾动作**一步都没做**。

---

## 二、A · bundle 本体复核（独立实测）

我没用 CodeBuddy 的验证脚本（它在 `$env:TEMP`，我看不到内容），自己跑了一遍：

### 文件清单（4 个，`locale/` 单独计）

```
README.md          4536 B
cordis.patch.yml   3412 B
icon.svg           1216 B
package.json        294 B
locale/en.json
```

### package.json —— 全部合规

| 字段 | 值 | 判定 |
|---|---|---|
| `name` | `@local/dsh-scipal` | ✅ 唯一、带 scope |
| `version` | `1.0.0` | ✅ |
| `private` | `true` | ✅ |
| `type` | `module` | ✅ |
| `exports` | `./locale/*.json` + `./icon` | ✅ 与官方 `host-plugin.md:46` 一致 |
| `files` | patch / locale / icon | ✅ |
| `dsh.bundle.patch` | `./cordis.patch.yml` | ✅ 是 **bundle** 层 |
| `dsh.profile` | **不存在** | ✅ 正确（误用 `dsh.profile.bundles` 是常见错） |

### cordis.patch.yml —— 三条铁律全部落实

```
顶层类型   : list len = 1
首条 keys  : ['insert']      ← 必须是 insert，写成顶层 - id: 会静默跳过（踩过）
insert 条数: 2
  - id=mcp-scipalhello  serverName=scipalhello  合法=True  stdio  failOnStartup=True
  - id=mcp-scipal       serverName=scipal       合法=True  stdio  failOnStartup=False
```

- ✅ 两条都在 `insert:` 内（不是顶层 `- id:`）
- ✅ `serverName` 都匹配 `^[A-Za-z0-9_-]{1,32}$`
- ✅ 哨兵 `failOnStartupError: true`，真实 server 设 `false` 且注释说明了理由（不拖垮哨兵）
- ✅ 保留了 `no_proxy` 说明与诊断矩阵注释

### locale / icon

- `locale/en.json`：`meta.title = "SciPal Literature Tools"`，description 236 字符 ✅
- `icon.svg`：1216 B（上限 262144）✅，根标签 `<svg xmlns="http://www.w3.org/2000/svg" …>` ✅

### 对照官方 `host-plugin.md` 安装前清单

| 官方要求 | 状态 |
|---|---|
| 唯一 name / version / `dsh.bundle.patch` | ✅ |
| `exports` 含 `./locale/*.json` 与 `./icon` | ✅ |
| `files` 含 patch/locale/icon | ✅ |
| `locale/en.json` 有 `meta.title` / `meta.description` | ✅ |
| 图标 ≤256KiB 且在包内 | ✅ |
| **补用户语言 locale（zh）** | ❌ **缺** —— 这就是 E-1 |

---

## 三、B · 收尾工单 E-1 ~ E-4：全部未执行

实测四个交付物**一个都不存在**：

```
packages/dsh-scipal/locale/zh.json      ❌ 不存在
packages/dsh-scipal/INSTALL.md          ❌ 不存在
scripts/precheck_dsh_bundle.py          ❌ 不存在
tests/backups/                          ❌ 不存在
```

`git status` 干净（除别人的 `_test_v3317b.py`），**没有任何新提交**。

### 原因（CodeBuddy 的原话）

> 「本工单在本会话早些时候已完成并提交（`2457e85`）……无需重做。」
> 「另外注意到工作区新出现了一个未跟踪文件 `docs/工单-bundle收尾.md` —— 如果那是下一轮的工单，你把它发我就行。」

**是沟通误会**：它看到 `docs/工单-bundle收尾.md` 是未跟踪的新文件，以为那是「下一轮」的东西，
而把自己已经做过的 `2457e85`（bundle 本体）当成了本次工单的全部内容。

实际上 `2457e85` 是**上一轮**（阶段五-A 主体），`工单-bundle收尾.md` 是**本轮**（E-1~E-4）。
→ 需要**明确告知它：这份工单现在就要做，不是下一轮。**

---

## 四、🔴 C · 新发现：README 的还原命令会抹掉账户配置

### 事实

`packages/dsh-scipal/README.md:38` 提供的还原命令是：

```powershell
Copy-Item "D:\sciPal\tests\cordis.patch.yml.bak" "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml" -Force
```

而 `tests/cordis.patch.yml.bak` **只有 297 字节**（阶段零基线，只有 `- id: locale` 一条）。

当前 `~/.dsh/profiles/desktop/cordis.patch.yml` 是 **4209 字节 / 6 条顶层条目**，实测结构：

| # | id | 内容 |
|---|---|---|
| 0 | `locale` | `preference: en` |
| 1 | `agent-default-model` | `deepseek-account` / `deepseek-flash` / `reasoningEffort: high` |
| 2 | **`ui-settings-account`** | **账户状态**：`step: done`、`purpose`、`process`、`completion: skipped`、`usage: compact`、`developerTools` |
| 3 | `ui-chat` | `transcriptView: standard`、`performanceUsage: compact` |
| 4 | `ui-settings` | `enabled: False` |
| 5 | `insert` | 两条 MCP（`scipalhello` / `scipal`）—— **这是要清掉的** |

### 风险

README 第 41-43 行确实有警告（说会抹掉 `agent-default-model`、`ui-*`），**但没说清第 2 条是账户状态**。
一旦误执行，会连带丢掉 DSH 账户的引导状态和界面偏好 —— 这不是「配置」丢了，是**用户状态**丢了。

### 正确做法（给人工步骤用）

**不要整体还原基线。** 只删除第 5 条那个 `insert` 块（两条 MCP），保留第 0-4 条。

→ 这条已作为 **E-5** 补进工单：README 要把警告改具体，并给出「只删 insert 块」的精确做法。

---

## 五、待办

| # | 事项 | 归属 |
|---|---|---|
| E-1 | 补 `packages/dsh-scipal/locale/zh.json` | CodeBuddy（未做） |
| E-2 | 写 `scripts/precheck_dsh_bundle.py`（只读诊断 + 仓库内备份 + 冲突扫描） | CodeBuddy（未做） |
| E-3 | 写 `packages/dsh-scipal/INSTALL.md`（DSH 会话内四步原文） | CodeBuddy（未做） |
| E-4 | README 补「卸载」章节 | CodeBuddy（未做） |
| **E-5** | **README 还原警告改具体**：点明会丢 `ui-settings-account` 账户状态，给出「只删 insert 块」的做法 | CodeBuddy（新增） |
| — | bundle 实装（关 DSH → 删 insert 块 → `install_bundle` → 重启 → 数工具） | **人** |

---

## 六、回归

- `self_check.py`：**110 通过 / 1 失败 / 121**（CodeBuddy 报告，与基线一致）
- 工作区无新增改动，`packages/dsh-scipal` 无未提交内容
