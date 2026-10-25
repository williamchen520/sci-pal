# DSH（DeepSeek Harness）契约要点 — 核对于官方文档

> **性质**：本文是对 DSH 官方文档的**摘录与核对**，用于 SciPal 插件化决策。
> 凡本文写明的字段，均可在对应原文中查到；凡本文标注「未证实」的，说明官方原文里找不到，**不要按传闻实施**。
> 采集时间：2026-10-24 ｜ 采集人：WorkBuddy

---

## ⚠️ 重大更正（2026-10-24 二次核对，优先级高于正文）

第一次核对只看 GitHub 文档，有两处判断错了。二次核对改为**直接解包本机 DSH 安装（`app.asar`，182 MB）**，拿到了随安装发布的官方原文，据此更正：

### 更正 1：新增 MCP 服务器必须用 `insert:`，不能直接写顶层 id

官方模板 `skills/cordis-plugin-development/templates/mcp/cordis.patch.yml` 原文照录：

```yaml
- insert:
    - id: demo-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: demo
        transport: streamable-http
        url: http://127.0.0.1:3000/mcp
        failOnStartupError: true
```

官方 `cordis-composition-reference` 的 loader 方言原文：

> - `insert: [rows]` appends rows; with an `id` naming an existing `group: true` row, the rows are appended inside that group's `config` list.
> - A patch with an `id` and no `insert` targets the existing row with that id. ...
> - **Non-insert patches without a nonempty `id`, and targets that match no row, are warned about and skipped.**

**我们第一版写的正是「有 id、无 insert、且 id 不存在」→ 被 warn 并跳过。** 实测日志原文：

```
[warn] patch: entry "mcp-scipalhello" not found [host.kernel.root]
```

⚠️ 正文第 3.1 节照录的 S5「最小配置」是**最终组合结果**的形态，不是 patch 层的写法。**照它写会失败。**

### 更正 2：`failOnStartupError` 必须是 `true`

官方模板写 `true`，我们第一版写 `false`（那是默认值）。`false` 的后果是**失败静默**——不报错、不提示，工具列表里就是没有。这正是这次「查不出原因」的根源。诊断期间务必设 `true`。

### 更正 3：`@deepseek-ai/dsh-mcp-client` 本机**已存在**，不需要联网安装

它就打包在 Electron 应用内：

```
app.asar → dsh/node_modules/@deepseek-ai/dsh-mcp-client/
├── README.zh.md   (17,063 B，官方中文说明)
├── lib/index.js   (35,041 B)
└── package.json   version 0.2.1-rc.2
```

`version 0.2.1-rc.2` 与 CLI 版本完全一致。之前「`profiles/desktop/node_modules` 里没有」的判断来自看错了目录——那个目录只放**用户后装的**包，随安装发布的包不在这里。

✅ 已把官方原文解包到仓库：`docs/DSH官方参考/`（18 个文件），CodeBuddy 直接读原文即可，不要再猜。

### 更正 4：官方不鼓励手写 `cordis.patch.yml`

`SKILL.md` 原文：

> For implementation, use ordinary workspace files to author a bundle, then `plugin_manager` with `action: install_bundle` and the absolute package directory as `target` ...
> **Do not write the profile's `package.json` or `cordis.patch.yml`**, create packages under `$DSH_HOME`, or run pnpm in the profile directory.

正确姿势：在工作区写 bundle → 用 `plugin_manager` 的 `install_bundle` 安装。
但 `plugin_manager` 是 **DSH 运行时内部工具**，CodeBuddy 没有；而 `desktop` profile 又被 Electron 独占、CLI 管不了。
**结论：从外部只能手改 YAML**（有备份 + 冻结分支兜底，风险可控），但必须用 `insert:` 写法。

---

## 0. 文档来源

| 编号 | 内容 | 地址 |
|---|---|---|
| S1 | MCP 子系统规范（中文） | `docs/subsystems/mcp.zh.md` |
| S2 | 工具契约参考（adding-a-tool） | `docs/cookbook/adding-a-tool.md` |
| S3 | 工具子系统参考页 | `reference/subsystems/tools` |
| S4 | Cordis 入门（inject / Service / 生命周期） | `docs/cordis-primer.zh.md` |
| S5 | MCP 客户端包（`dsh-mcp-client` 配置字段） | `packages/mcp/mcp-client/README.zh.md` |

仓库：`github.com/deepseek-ai/deepseek-harness`，分支 `master`。

---

## 1. 最关键的一条：DSH 是 TypeScript，SciPal 是 Python

S2/S3 的所有示例均为 `.ts`，导入 `@deepseek-ai/cordis`、`@deepseek-ai/dsh-tools`；
`dsh-research-kit` 的官方要求为 **Node.js >= 22.6**。

**SciPal 是 Python**（Flask + ChromaDB + Ollama + scispacy，157 个 `.py`、45,290 行）。

→ **插件化不等于「把 Python 模块改写成 DSH 插件」。** 那是换语言重写 4.5 万行。
→ 正确路径：**Python 侧不动，用 MCP 作为跨语言桥**（见第 3 节）。

---

## 2. 工具插件契约（S2 / S3 原文）

### 2.1 最小形态（S2，原文照录）

```ts
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'my-tool'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'read_file',
    description: 'Read a file from disk.',
    parameters: {
      path: { type: 'string', required: true, description: 'Absolute path' },
      limit: { type: 'number' },              // 可选（required 是逐属性的）
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args, exec) {
      return readFile(args.path, { encoding: 'utf8', signal: exec.signal })
    },
  }))
}
```

### 2.2 `defineTool` 字段清单

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `name` | ✅ | 工具名。`run_code` 为保留名，不可用 |
| `description` | ✅ | 模型看到的部分 |
| `parameters` | ✅ | `ParameterSchemaSpec`；**逐属性**标 `required: true`，根对象默认开放 |
| `output.schema` | ✅ | `ValueSchemaSpec` → 编译为 JSON Schema；根可为 object / array / scalar / null |
| `output.render` | ✅ **必填** | `(args, value) => ContentBlock[]`，纯函数，模型看到的呈现 |
| `execute` | ✅ | `(args, exec)`；**只返回 canonical JSON 值**，不返回 content blocks |
| `output.presentationMeta` | 可选 | 可重放的 UI 元数据投影 |
| `timeoutMs` | 可选 | 协作式超时（毫秒）；**永不发给模型** |
| `isConcurrencySafe` | 可选 | 只有**精确返回 `true`** 才并发，其余一律 `exclusive`（fail-closed） |
| `presentCall` / `presentResult` | 可选 | UI 卡片，必须**纯函数**（会在会话重放时跑），不得有 I/O |
| `projectContent` / `finalizeContent` | 可选 | 内容安装 / 末段变换；`finalizeContent` **必须 total，不得 throw** |

> ⚠️ 常见遗漏：`output.render` 是**必填**字段，不是可选。只写 `output.schema` 会缺模型可见内容。

### 2.3 `execute` 的错误约定（S2 原文）

- **基础设施故障 → `throw`**；注册表捕获后转为 `isError` 结果，**不会让 `ctx.tools.execute` reject**。
- **业务上的「非理想结果」→ 仍返回 canonical 值**（例如进程非零退出也算一次成功调用）。
- 参数不匹配 → `ToolArgsError`（`INVALID_ARGS`）；返回值不合 schema → `ToolOutputError`（`INVALID_TOOL_OUTPUT`）。
- `exec.signal` **必须被遵守**（取消时要停手）。

### 2.4 PTC 模式红利（S2）

> 「In PTC mode, every visible registered tool is available as `await tools.<name>(args)` without extra integration.」

即：工具一旦注册，**自动**获得程序化调用能力，无需额外适配。
→ 因此 `output.schema` 要设计成**好用的程序化 API**：直接返回句柄和字段，**不要让人解析散文**。

---

## 3. MCP 是跨语言的正解（S1 / S5）

### 3.1 最小配置（S5 原文，YAML）

```yaml
- id: mcp-scipal-search
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: scipal-search        # 必填，[A-Za-z0-9_-]{1,32}，作用域内唯一
    transport: stdio                 # stdio | streamable-http
    command: python                  # ← 可以是 Python 解释器
    args: ['-m', 'scipal_mcp.search']
    env:
      SCIPAL_DATA_DIR: '!!js process.env.SCIPAL_DATA_DIR'
    cwd: D:/sciPal
```

**含义**：`transport: stdio` 会启动一个**本地子进程**，该子进程可以是 Python。
→ **SciPal 每个域写一个 Python MCP Server，DSH 侧只加一条 YAML 配置，零 TypeScript 代码。**

### 3.2 配置字段全表（S5）

| 字段 | 默认值 | 含义 |
|---|---|---|
| `transport` | 必填 | `stdio` 或 `streamable-http` |
| `serverName` | 必填 | 工具名 namespace；`[A-Za-z0-9_-]{1,32}` |
| `command` / `args` / `env` / `cwd` | — | stdio 用 |
| `url` / `headers` | — | streamable-http 用 |
| `toolCallTimeoutMs` | **60,000** | 单次 `tools/call` 超时 |
| `maxInstructionBytes` | 32,768 | 服务器指令字节上限，超出**连接失败** |
| `failOnStartupError` | `false` | 启动失败是否拒绝插件激活 |
| `reconnect.enabled` | `true` | 断线自动重连 |
| `reconnect.initialDelayMs` / `maxDelayMs` / `maxAttempts` | 500 / 30,000 / 10 | 退避与尝试预算 |

### 3.3 工具命名（S5）

公开名为 **`mcp__<serverName>__<rawName>`**（如 `mcp__github__create_issue`）。
`tools/call` 发给服务器的**始终是原始名**；公开名不会发给服务器。
两个服务器可以有同名工具，各自 namespace 下共存。
→ 名称在重启/重载后保持稳定，因此**会话历史与权限规则持续有效**。

### 3.4 ⚠️ MCP 的硬限制（对 SciPal 有直接影响）

1. **`toolCallTimeoutMs` 默认 60 秒** —— SciPal 的 PDF 解析、批量下载、综述生成全部会超时。
2. **不支持「基于任务的执行」（task-based execution）** —— 要求该扩展的工具**在调用时被直接拒绝**。
3. **stdio 子进程环境被清洗**：删除所有匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的环境变量，**以及所有 `DSH_*`**。
   → SciPal 的密钥必须在 `env:` 里**显式重填**，不能指望继承父进程。
4. **不支持**：MCP 提示词模板、人工输入征询（elicitation）、资源订阅。
5. 图片仅 PNG / JPEG / WebP / GIF 可持久化；音频与嵌入资源不进模型上下文。
6. 连续重连失败 10 次 → 工具被移除，直到重载配置或重启。
7. MCP 客户端**不发布共享的 `ctx.mcp` 服务**（S1 原文）。→ **`inject: ['mcp']` 不存在**，别写。

> **对第 1、2 条的应对**：长任务不要做成「一次长 MCP 调用」，
> 而应当**立即返回一个 job 句柄**，再用独立的状态工具轮询。
> 这与 DSH 官方的后台任务形态一致（S2：`{ kind: 'background', jobId }`）。
> **SciPal 已经具备这套轮询基础设施**：`/api/tasks/<task_id>`、`/api/review/task/<task_id>`、
> `/api/search/download_status`、`/api/search/download_queue` —— 天然对得上。

---

## 4. `inject` 与 Cordis 语义（S4）

> 「**插件是实现 Service 的对象。** 它可以是一个带有可选 `inject` 和 `apply(ctx)` 字段的函数，
> 也可以是一个 `Service` 子类。」
> 「通过 `inject` 声明服务依赖。插件声明所需的服务后，**会等待这些服务就绪才启动**；
> 加载顺序通过服务依赖表达，而非手动编排启动序列。」

- 服务占据稳定的 `ctx.<key>`，其他插件**按 key 查找**，不导入具体实现。
- 已知服务 key：`tools`、`llm`、`sessions`、`agents`、`jobs`、`mcpResources`。
- **注册是可逆的副作用**：`ctx.effect()` / `ctx.on()` 安装的注册，reload 与 teardown 时按预期撤销。
- 每个注册都应有对应 disposer。

> 「漏写一个硬依赖 → 插件永远停在 PENDING」这个说法：**实质正确**（是等待，不是报错），
> 但**只在写 TypeScript 插件时才构成风险**。
> 走 MCP 配置路线（第 3 节）**不写插件代码，`inject` 这项风险直接归零**。

---

## 5. 玄木方案逐条核对表

| # | 玄木的说法 | 官方核对结果 | 判定 |
|---|---|---|---|
| 1 | `export const name` + `inject = ['tools']` + `apply(ctx)` | S2 原文一致 | ✅ 正确 |
| 2 | `ctx.tools.register(defineTool({...}))` | S2 原文一致 | ✅ 正确 |
| 3 | 必须声明 `parameters` 与 `output.schema` | 正确，但**漏了必填的 `output.render`** | ⚠️ 缺一项 |
| 4 | `execute` 只返回 canonical 值；基础设施 throw，业务非理想仍返回值 | S2 原文一字不差 | ✅ 正确 |
| 5 | `export default class extends Service` | S4 确认「也可以是 Service 子类」，但**没给具体写法** | ⚠️ 方向对，细节未证实 |
| 6a | `cordis.patch.yml` | **存在于本机** `~/.dsh/profiles/desktop/cordis.patch.yml`——但它是 **profile 的补丁层**，不是插件自带的文件 | ✅ 存在，但**归属说错了** |
| 6b | `package.json` 的 `dsh.bundle.patch` | 五份文档未出现；本机 `package.json` 实际字段是 **`dsh.profile.bundles`**，不是 `dsh.bundle.patch` | ❌ 字段名错 |
| 7 | `dsh plugin --profile web add link:$(pwd)/...` | 命令形态对，但 **profile 名在本机是 `desktop` 不是 `web`**；`link:` 前缀未证实 | ⚠️ 部分证实 |
| 8 | `dsh --profile web --dump-config` | 五份文档中未出现 | ⚠️ 未证实 |
| 9 | inject 漏写 → PENDING 卡死 | S4「等待这些服务就绪才启动」 | ✅ 实质正确 |
| 10 | **优先复用 `dsh-research-kit`，工作量小一个量级** | 见第 6 节 | ❌ **重大误判** |

---

## 6. `dsh-research-kit` 究竟是什么

**真实存在**：`github:fsrmqi/dsh-research-kit`，v0.3.0，MIT，2026-10-05 更新。
安装：`npx -p @deepseek-ai/dsh dsh plugin --profile web add github:fsrmqi/dsh-research-kit`

内容：351 条科研工作流（28 个流程族）、109 个技能条目、129 个科学数据源（其中 11 个支持直查）。

**但它与 SciPal 几乎不重叠**，官方定位写得很清楚：

- 运行在**浏览器侧**，是一个 **Prompt 组装器**：「把工作流和用户参数组装成可编辑 Prompt，
  并由 DSH 当前会话负责实际发送与执行」
- **不持有模型密钥**（DSH 侧复用当前会话模型路由，MCP 侧不托管模型）
- **不代为执行工具**（"it does not execute any tools on the user's behalf"）
- **不读取文件内容**、不重造文件上传（材料引用走 DSH 原生 `@文件`）
- 未接通数据源时**明确回退到 DSH Agent/MCP**

→ **它提供的是「提示词模板 + 工作流目录」，SciPal 提供的是「真检索 + 真数据库 + 真模型 + 425 MB 存量数据」。**
两者是互补关系，不是替代关系。玄木说「优先复用、工作量小一个量级」不成立。

**唯一真正值得复用的一点**：它自带的 **stdio MCP Server**（文献检索、证据管理、研究运行、审阅）
兼容 Codex / Claude Code / Zed 等宿主 —— 也就是说生态位与我们打算做的 SciPal MCP Server 是**同类**。
可以参考它的工具划分方式，但**不能指望它替我们干检索**。

---

## 6.5 本机 DSH 安装实况（2026-10-24 实测）

| 项 | 实测 |
|---|---|
| 形态 | **DSH Desktop**（Electron 桌面版），**不是 CLI** |
| `dsh` 命令 | **不在 PATH 里**（`which dsh` 为空）→ 只能用 `npx -p @deepseek-ai/dsh dsh …` 或桌面 UI |
| Node.js | v22.22.2（≥ 22.6，满足要求） |
| 配置根 | `C:\Users\chenwei\.dsh\` |
| **profile 名** | **`desktop`**（不是玄木说的 `web`） |
| profile 目录 | `C:\Users\chenwei\.dsh\profiles\desktop\` |
| 已有 bundle | `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-web-app`（在 `package.json` 的 `dsh.profile.bundles`） |
| `profiles/node_modules` | **当前为空**（bundle 尚未落地到此，或装在别处） |
| MCP 配置入口 | ❌ **桌面端无 MCP/工具配置 UI**（用户 2026-10-24 实测确认）→ **只能手改 `cordis.patch.yml`** |
| 是否可离线改配置 | ✅ 可以，且**应当在 DSH 关闭时改**（开着改可能被退出时的状态写回覆盖） |
| 验证方式 | ⚠️ **必须启动 DSH 后由人肉眼看工具列表** —— 无 CLI，agent 无法自助验证 |

### 三个文件的真实内容（原文照录）

**`cordis.yml`** —— 空数组，**官方明示不要改它**：
> 「dsh profile root — an empty entry list. The tree is composed as patches:
> each bundle in package.json's `dsh.profile.bundles`, then `cordis.patch.yml`, then any
> `--patch` overlays. **Edit `cordis.patch.yml`, not this file.**」

**`cordis.patch.yml`** —— 空数组，这是**我们要写的地方**：
> 「Your patch layer for this dsh profile, applied **after every bundle layer**:
> a top-level YAML array of loader patch entries (id-targeted config overrides, disables,
> and insert lists; `!!js` expressions allowed).」

**`package.json`**：
```json
"dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"] } }
```

→ **结论：在本机加一个 MCP 服务器，正确做法是往 `cordis.patch.yml` 里追加一条
`@deepseek-ai/dsh-mcp-client` 条目**（与 S1「在目标 Cordis 作用域中，为每台服务器配置一个
`@deepseek-ai/dsh-mcp-client` 条目」完全吻合），而不是去动 `cordis.yml` 或 bundle。

---

## 7. 由此得出的实施路线（供阶段三裁决）

| 路线 | 做法 | TS 代码量 | 风险 |
|---|---|---|---|
| **A · MCP stdio（推荐）** | 每个 SciPal 域一个 Python MCP Server；DSH 侧加 YAML 条目 | **几乎为零** | 低（Python 侧不动） |
| B · streamable-http | 直连现有 Flask `api_server.py` | 零 | 中（60s 超时、常驻服务生命周期不受 DSH 管） |
| C · TS 插件 + Python 子进程 | 真写 DSH 插件 | 大 | 高（等于新写一套 TS 层） |

**路线 A 的直接收益**：玄木流程里的**阶段四（逐块重写）与阶段五（inject 交叉核对）基本可以取消** ——
没有 TS 插件就没有 `inject` 要核对。

**待办前置（阶段零）**：先用官方最小配置跑通一个现成 MCP server，验证工具确实出现在模型工具列表里。
这一步**不需要写任何代码**，只需一条 YAML。

---

## 8. 阶段零结论与阶段三裁决（2026-10-24 14:00）

### 8.1 阶段零：✅ 通过

`tests/mcp_ping_server.py` 经 `insert:` 方式挂进 `desktop` profile 后，DSH 设置页出现：

| 位置 | 显示 |
|---|---|
| Managed by another plugin | `scipalhello` · stdio |
| Registered MCP tools | `mcp__scipalhello__ping` |
| Configured servers | 0（正常 —— 不是 UI 配的，是 profile patch 层注入的，故 UI 内为 Read-only） |

**结论：Python 侧一行不改，DSH 能拉起 stdio 子进程并把工具注册进模型工具列表。**
路线 A 的前提条件成立，玄木方案里的「换语言重写」彻底作废。

### 8.2 阶段三裁决：**A-1 薄转发**（「单进程」已于阶段五-B 修订为按业务流拆分）

> **MCP 侧不承载任何业务逻辑，只把 MCP 工具调用转发到 SciPal 已有的 Flask API。**

> 🔴 **2026-10-24 修订（阶段五-B 实测推翻了下文「只做一个 server」的结论，请以下面这段为准）**
>
> 原文用「显存」论证不能拆 server，**前提是错的**：只有 import 了业务模块的进程才会加载模型，
> 而薄转发的 MCP 进程**一个模型都不加载**。实测单个 MCP server 常驻 ≈ **68 MB**，
> 模型仍然只存在于 5000 端口那**一个** Flask 进程里 —— 拆 server **不复制模型**，VRAM 不变。
>
> 真正的约束是**模型上下文与工具选择准确率**：单 server 塞的工具越多，上下文越挤、选错越多。
> 故实际做法是 **按业务流拆、每 server 以 8 个为基准**（现为 `scipal-search` **10** + `scipal-generate` 9
> + 哨兵 `scipalhello` 1，共 **20**）。命名空间因此是多前缀（`mcp__scipal-search__*`），
> 不再是单一 `mcp__scipal__*`。超出 8 的部分都是「同一工作流闭环」的破例（详见
> `docs/DSH插件化-路线图.md` §2.3）。
>
> 下方原始论证保留作历史记录，**不要再据此把 server 合并回一个**。

**原始论证（2026-10-24 早期，结论已被推翻）：**

| 事实 | 后果 |
|---|---|
| SciPal 的 embedding / Cross-Encoder reranker / ChromaDB 都是**进程级资源** | 每个 MCP server 都是独立 Python 进程 → 拆 9 个 = 9 份模型 |
| 本机 RTX 4060 **8 GB** | 装不下第二份，更别说 9 份 |
| Flask 进程本来就常驻并已加载全部模型 | 转发是**零增量成本**；新起进程是**全量成本** |

**故（原始结论，已作废）：单进程 + 扁平命名空间**（`mcp__scipal__<tool>`），宁可粗，不要碎。

**三条硬性设计约束（约束 1、2 仍有效，新增 3）：**

1. **MCP server 必须是纯 HTTP 客户端** —— 禁止 `from services...`、禁止 sys.path 注入项目根。
   一旦 import 了 SciPal 内部模块，就会把模型一起加载进子进程，「轻薄转发」立刻失效。
   （唯一允许的 `sys.path.insert` 是把 `mcp_server/` 自己插进去，用于 `import _forward`。）
2. **不许改 Flask 业务代码** —— 需要新能力就调现有路由；路由不够再加，但那是另一张工单。
3. **绝不向 stdout 打印** —— stdio 模式下 stdout 是 JSON-RPC 通道，一行 `print()` 就毁掉协议。

**长任务处理**：MCP 的 `toolCallTimeoutMs` 只有 60 秒，且**不支持 task-based execution**。
SciPal 现成有轮询设施（`/api/tasks/<id>`、`/api/review/task/<id>`、`/api/search/download_status`），
所以长任务工具一律「**立即返回 job 句柄 + 独立的 status 工具轮询**」，不做同步等待。
