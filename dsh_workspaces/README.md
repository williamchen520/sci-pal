# DSH 会话模板（workspace AGENTS.md）

DSH 会按 workspace 加载 `AGENTS.md`。这里提供三套：

| 目录 | 数据等级 | 模型 | 工具 |
|---|---|---|---|
| `raw/` | 原始数据（xlsx/csv/tsv/docx） | 本地 qwen2.5:3b | `scipal-data` |
| `public/` | 公开文献 | 云端大模型 | `scipal-search` |
| `mixed/` | 本地准备 → 云端综合 | 本地 + 云端 | 两阶段 |

## 使用方式

1. 在 DSH 中新增 workspace，路径分别指向：
   - `D:\sciPal\dsh_workspaces\raw`
   - `D:\sciPal\dsh_workspaces\public`
   - `D:\sciPal\dsh_workspaces\mixed`
2. 打开对应 workspace 会加载该目录的 `AGENTS.md`；
3. 在模型选择器里选：
   - raw：本地 `qwen2.5:3b`
   - public：云端大模型
4. `scipal-data` MCP server 已加入 `packages/dsh-scipal/cordis.patch.yml`；
   **改 bundle 后需完全退出 DSH 再启动**。

## 说明

- DSH 目前没有“会话模板”独立配置项，workspace + `AGENTS.md` 是最接近的原生机制；
- 真正的强制隔离仍在 SciPal 侧：raw 会话不挂云端工具、`cloud_gate` 校验、审计；
- 模板中的模型名是建议值，实际以 DSH 模型选择器为准。
