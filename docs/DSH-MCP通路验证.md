# DSH × SciPal · MCP 通路验证（阶段零 A）

> **状态**：只备份、只起草。**本次未向 `~/.dsh/` 写入任何内容。**
> **完成后由用户人工验证**：DSH Desktop 无 CLI，工具是否出现必须靠肉眼确认（见 `docs/DSH契约要点.md` 6.5）。
> 生成时间：2026-10-24 ｜ 仓库分支：`dev`

---

## 1. 配置备份（仓库外，git 救不回来）

| 项 | 值 |
|---|---|
| 源文件 | `C:\Users\chenwei\.dsh\profiles\desktop\cordis.patch.yml` |
| 备份文件 | `tests/cordis.patch.yml.bak` |
| 源文件大小 | **297 bytes** |
| 备份大小 | **297 bytes** |
| 源文件 SHA256 | `249ADD6555BB82DD1C7008237623E7ED05E62D43AC39A20A80A0DD239A803D85` |
| 备份 SHA256 | `249ADD6555BB82DD1C7008237623E7ED05E62D43AC39A20A80A0DD239A803D85` |
| 一致性 | ✅ 同字节（哈希、长度均一致） |

**回滚命令**（如写入后需还原）：

```powershell
Copy-Item "d:\sciPal\tests\cordis.patch.yml.bak" "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml" -Force
```

> ⚠️ 写入 DSH 配置应在 **DSH Desktop 关闭时**进行，否则退出时的状态写回可能覆盖手工修改。

---

## 2. 最小 MCP Server（已可运行）

| 项 | 值 |
|---|---|
| 脚本 | `tests/mcp_ping_server.py` |
| 性质 | 临时验证脚本，**不属于业务代码**，不 import `services/`、`api_server.py`、`config/` |
| SDK | 官方 `mcp` **v2.2.0**（实测于 `venv_sciPal_py312`） |
| 服务名 | `scipalhello` / version `0.1.0` |
| 暴露工具 | **1 个**：`ping` → `{"ok": true}`（`structured_output=True`，返回类型 `PingResult(TypedDict)`） |
| transport | `stdio` |

**关于 mcp 2.x 的实测差异**（写代码时踩到，记录备查）：

| 1.x 写法 | 2.x 实际 |
|---|---|
| `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer`（`fastmcp` 已抛出迁移提示） |
| `FastMCP("name")` | `MCPServer("name", version=...)` |
| `result.isError` / `result.structuredContent` | `result.is_error` / `result.structured_content`（snake_case） |
| `structured_output` 可用 `dict` 注解 | 必须是可序列化 schema（`dict` 会抛 `InvalidSignature`），故用 `TypedDict` |

### 2.1 自测命令（可直接复制运行）

```powershell
cd d:\sciPal
.\venv_sciPal_py312\Scripts\python.exe tests\mcp_ping_server.py --selftest
```

**实测输出**：

```text
[selftest] serverName   : scipalhello 0.1.0
[selftest] tools        : ['ping']
[selftest] is_error     : False
[selftest] payload      : {'ok': True}
[selftest] RESULT       : PASS
```

**这说明什么**：`--selftest` 会以 `sys.executable` 启动**本文件自己的独立 stdio 子进程**，完成 `initialize` → `tools/list` → `tools/call(ping)` 全链路，并校验 `is_error=False`、payload 等于 `{"ok": true}`、工具清单恰为 `['ping']`。即：该脚本作为独立 stdio 进程可以正常应答 MCP 协议。

**注意**：`--selftest` 是 client 身份（可向 stdout 打印）；不带参数时为 server 身份，**stdout 是 JSON-RPC 通道，脚本不向 stdout 打印任何内容**。

---

## 3. 待写入的 YAML 片段（**待用户写入，本次未落盘**）

> **写入位置**：`C:\Users\chenwei\.dsh\profiles\desktop\cordis.patch.yml` 的**顶层数组末尾**（追加，不要覆盖已有 `- id: locale` 条目）。
> **格式依据**：`docs/DSH契约要点.md` 3.1 / 3.2（`@deepseek-ai/dsh-mcp-client` 的 `config` 字段）。

### 3.1 条目一：`hello`（验证「npx + 官方 GitHub MCP Server」通路）

```yaml
- id: mcp-hello
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: hello
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      # stdio 子进程环境会被清洗（见第 4 节），密钥必须在 env 里显式声明
      GITHUB_PERSONAL_ACCESS_TOKEN: '在此填写你的 PAT'
    toolCallTimeoutMs: 60000
    failOnStartupError: false
```

- `args` 中的 `-y` 用于非交互式安装：`npx` 首次拉包时会询问 `Ok to proceed? (y)`，在 DSH 拉起的无 TTY 子进程里会**直接卡死**。
- `toolCallTimeoutMs` 显式写成默认值 60,000，便于后续对长任务单独调整。

### 3.2 条目二：`scipalhello`（验证「Python stdio MCP Server」通路）

```yaml
- id: mcp-scipalhello
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: scipalhello
    transport: stdio
    command: 'D:/sciPal/venv_sciPal_py312/Scripts/python.exe'
    args: ['D:/sciPal/tests/mcp_ping_server.py']
    cwd: 'D:/sciPal'
    env:
      PYTHONUTF8: '1'
    toolCallTimeoutMs: 60000
    failOnStartupError: false
```

**为什么 `command` 用 venv 绝对路径而不是 `python`**：
本机 PATH 上的 `python` 是系统解释器 `C:\Users\chenwei\AppData\Local\Programs\Python\Python312\python.exe`，实测**未安装 `mcp` SDK**（`self_check.py` 在系统 Python 下报 flask/pydantic/chromadb 全部未安装，且 `import mcp` 失败）。只有 `venv_sciPal_py312` 里是 mcp v2.2.0。用 `python` 会 `ModuleNotFoundError: No module named 'mcp'`，而 `failOnStartupError: false` 会让失败**静默**，只得在 DSH 工具列表里看不到而不知道原因。

**预期结果（用户肉眼验证）**：DSH 重启后，模型工具列表中出现 `mcp__scipalhello__ping`；调用它应返回 `{"ok": true}`。

### 3.3 合并后的完整文件（写入时应呈现如下，共 3 个顶层条目）

```yaml
# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; `!!js` expressions allowed).
- id: locale
  name: "@deepseek-ai/dsh-client-locale"
  config:
    preference: en
- id: mcp-hello
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: hello
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: '在此填写你的 PAT'
    toolCallTimeoutMs: 60000
    failOnStartupError: false
- id: mcp-scipalhello
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: scipalhello
    transport: stdio
    command: 'D:/sciPal/venv_sciPal_py312/Scripts/python.exe'
    args: ['D:/sciPal/tests/mcp_ping_server.py']
    cwd: 'D:/sciPal'
    env:
      PYTHONUTF8: '1'
    toolCallTimeoutMs: 60000
    failOnStartupError: false
```

---

## 4. stdio 环境清洗的影响（必读）

依据 `docs/DSH契约要点.md` 3.4 第 3 条，`transport: stdio` 的子进程环境会被清洗：

> 删除所有匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的环境变量，**以及所有 `DSH_*`**。

### 4.1 对 SciPal 的具体影响

| 变量 | 是否被清洗 | 原因 |
|---|---|---|
| `SCIPAL_PROTOCOLS_IO_TOKEN` | ✅ 被删 | 命中 `TOKEN` |
| `NCBI_API_KEY` | ✅ 被删 | 命中 `KEY` |
| `OPENALEX_MAILTO` | ❌ 保留 | 不命中任何模式 |
| `SCIPAL_HOST` / `SCIPAL_DATA_DIR` 等 | ❌ 保留 | 不含 KEY/PASSWORD/SECRET/TOKEN，也不是 `DSH_` 前缀 |
| 任何 `DSH_*` | ✅ 被删 | 无条件删除 |

> 结论：**密钥不能指望继承父进程**。凡是含 KEY / PASSWORD / SECRET / TOKEN 的变量名，都必须在 YAML 的 `env:` 里**逐条显式写死**，否则子进程里读到的是空值，而报错通常出現在业务调用深处（而不是启动时）。

### 4.2 写法要求

```yaml
    env:
      SCIPAL_PROTOCOLS_IO_TOKEN: '<显式填写，不要写 ${...} 引用父进程>'
      NCBI_API_KEY: '<显式填写>'
```

- `env:` 中显式声明的键**不受清洗规则影响**（清洗作用于继承环境，不作用于显式声明）。
- 不要把密钥写进 `cordis.patch.yml` 后提交到任何仓库；该文件在 `~/.dsh/` 下，**不在 git 里**，这也是它需要单独备份的原因（见第 1 节）。
- `PYTHONUTF8: '1'` 建议保留：SciPal 侧多处文件读取依赖 UTF-8，Windows 默认代码页（cp1252）会引发 `UnicodeDecodeError`（本仓库 `self_check.py:575` 即为一例）。

---

## 5. 附录：`cordis.patch.yml` 原文照录

> 采集时刻（写入前）：2026-10-24 ｜ 297 bytes ｜ 与 `tests/cordis.patch.yml.bak` 同字节

```yaml
# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; `!!js` expressions allowed).
- id: locale
  name: "@deepseek-ai/dsh-client-locale"
  config:
    preference: en
```

---

## 6. 本次未做 / 待人工完成

| 项 | 状态 |
|---|---|
| 写入 `~/.dsh/profiles/desktop/cordis.patch.yml` | ❌ **未做**（工单要求本次只起草） |
| 启动 DSH 确认 `mcp__scipalhello__ping` 出现 | ⏳ 待用户人工验证（无 CLI） |
| 确认 `mcp__hello__*` 工具出现 | ⏳ 待用户人工验证；需先填入有效 PAT |
| `@modelcontextprotocol/server-github` 版本可用性 | ⏳ 未验证（本机未 `npm install -g`，依赖 `npx` 首次拉取） |
