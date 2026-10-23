# DSH（DeepSeek Harness）契约要点 — 核对于官方文档

> **性质**：本文是对 DSH 官方文档的**摘录与核对**，用于 SciPal 插件化决策。
> 凡本文写明的字段，均可在对应原文中查到；凡本文标注「未证实」的，说明官方原文里找不到，**不要按传闻实施**。
> 采集时间：2026-10-24 ｜ 采集人：WorkBuddy

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
| 6 | `package.json` 的 `dsh.bundle.patch` + `cordis.patch.yml` | S1–S5 **五份文档里一次都没出现** | ❌ 未证实 |
| 7 | `dsh plugin --profile web add link:$(pwd)/...` | 官方出现的是 `... add github:fsrmqi/dsh-research-kit`；**`link:` 前缀未证实** | ⚠️ 部分证实 |
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
