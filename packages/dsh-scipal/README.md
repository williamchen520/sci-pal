# dsh-scipal — SciPal MCP 配置型 bundle

把 SciPal 的 MCP server 条目从「手写 profile patch」升级成**可单独安装/卸载的插件**。
零代码：只有 `package.json` / `cordis.patch.yml` / `locale/en.json` / `icon.svg`。

包含两个 server 条目（故意的哨兵设计，见 `cordis.patch.yml` 注释）：

| id | serverName | 作用 |
|---|---|---|
| `mcp-scipalhello` | `scipalhello` | 零依赖哨兵，只提供 `ping`，用于区分故障在哪一侧 |
| `mcp-scipal` | `scipal` | 真实工具面（health / search_papers / get_paper / get_abstract / task_status） |

---

## 🔴 安装前必读：重名冲突会导致加载报错

官方 README 原文：

> **两条配置项使用相同的服务器名称时，后加载的一条会在加载时以明确错误失败。**

你现在的 `~/.dsh/profiles/desktop/cordis.patch.yml` 里**已经手写了** `mcp-scipalhello`
和 `mcp-scipal` 两条 `insert` 条目。**安装本 bundle 之前必须先删掉它们**，
否则 `scipalhello` / `scipal` 重名冲突，加载会直接报错。

**正确顺序**：

1. **关闭 DSH Desktop**（启动后 DSH 会回写该文件，开着改会被覆盖）
2. 打开 `C:\Users\<你的用户名>\.dsh\profiles\desktop\cordis.patch.yml`
3. **删除**文件末尾的 `- insert:` 块（即 `mcp-scipalhello` 与 `mcp-scipal` 两个条目
   及其上方 `# ===== SciPal MCP 服务器（两个，故意的）=====` 起的注释段）
4. 保存，然后安装 bundle（见下节）

### 还原命令（改坏了就用这个）

不装 bundle、想回到手写配置时，用仓库里的备份整文件还原：

```powershell
Copy-Item "D:\sciPal\tests\cordis.patch.yml.bak" "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml" -Force
```

> `tests/cordis.patch.yml.bak` 是阶段零 A 保存的**原始基线**（只有 `- id: locale` 一条）。
> 若你在手写阶段之后又加过其他 profile 条目（如 `agent-default-model`、`ui-*`），
> 这个还原会一并抹掉 —— 请先用 `Copy-Item` 把当前文件另存一份再还原。

---

## 安装

安装动作由 **DSH 运行时**执行，本仓库的 CodeBuddy 没有 `plugin_manager`，无法代劳：

在 DSH 会话里让 agent 调用 `plugin_manager`，`action: install_bundle`，
`target` 填本目录的**绝对路径**：

```text
D:\sciPal\packages\dsh-scipal
```

或走 DSH Desktop 的插件安装 UI（若提供该入口）。

安装成功后重启 DSH，工具列表应出现：

```text
mcp__scipalhello__ping
mcp__scipal__health
mcp__scipal__search_papers
mcp__scipal__get_paper
mcp__scipal__get_abstract
mcp__scipal__task_status
```

## 卸载

在 DSH 会话中让 agent 调用 `plugin_manager` 的移除/卸载动作，指向本 bundle（或走 UI）。
卸载后如需恢复手写配置，用上面的「还原命令」。

> 卸载**不会**删除 `~/.dsh/profiles/desktop/cordis.patch.yml`，也不会动 SciPal 仓库。

---

## 前置条件

| 依赖 | 说明 |
|---|---|
| `D:/sciPal/venv_sciPal_py312/Scripts/python.exe` | 必须存在且装了 `mcp` 2.2.0（系统 Python 没装） |
| `D:/sciPal/tests/mcp_ping_server.py` | 哨兵脚本，零依赖 |
| `D:/sciPal/mcp_server/scipal_server.py` | 真实工具面脚本（薄转发 Flask） |
| SciPal Flask API | `http://127.0.0.1:5000` 需在运行；可用 `scripts/sciPal_watchdog.py` 常驻守护 |

> bundle 里的路径是**绝对路径**（`D:/sciPal/...`）。换机器或换目录时需要改 `cordis.patch.yml`。

---

## 文件

```text
packages/dsh-scipal/
├── package.json        # dsh.bundle.patch → ./cordis.patch.yml
├── cordis.patch.yml    # 两个 server 的 insert 条目（含三条铁律注释）
├── locale/en.json      # 插件列表里显示的名称与描述
├── icon.svg            # 原创图标（文献页 + 检索放大镜）
└── README.md           # 本文
```

### `cordis.patch.yml` 里保留的三条铁律

1. 新增条目必须包在 `insert:` 里；写成顶层 `- id: xxx` 会被判定为
   “targets that match no row” → warn 并跳过，且**不报错**（静默失败）。
2. `failOnStartupError: true`；默认 false 会让启动失败静默跳过。
   （`mcp-scipal` 因依赖 Flask，仍保留 `false`，代价是靠哨兵对照观察。）
3. 改配置要在 **DSH 关闭时**做；启动后 DSH 会回写该文件。

---

## 本目录未做的事

- 未写入 `~/.dsh/` 下任何文件
- 未执行 `install_bundle`
- 未修改 `mcp_server/`、`services/`、`api_server.py`
