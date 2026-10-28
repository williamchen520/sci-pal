# DSH 配置：模型分层与数据隔离

> 配套：`docs/计划-模型分层与数据隔离.md`
> 目标：raw 会话只挂本地数据工具；云端模型只接收 `cloud-gate` 允许的聚合/脱敏产物。

## 1. MCP server 配置

```json
{
  "mcpServers": {
    "scipal-data": {
      "command": "python",
      "args": ["D:/sciPal/mcp_server/data_server.py"],
      "env": {
        "SCIPAL_API_BASE": "http://127.0.0.1:5000",
        "SCIPAL_API_TOKEN": "tok_local"
      }
    },
    "scipal-search": {
      "command": "python",
      "args": ["D:/sciPal/mcp_server/search_server.py"],
      "env": {
        "SCIPAL_API_BASE": "http://127.0.0.1:5000",
        "SCIPAL_API_TOKEN": "tok_local"
      }
    }
  }
}
```

- `scipal-data` 只连本机；
- 远端部署时把 `SCIPAL_API_BASE` 换成服务器地址，token 用 `SCIPAL_API_TOKENS` 中的值。

## 2. 模型配置

```yaml
default_model: cloud-large          # 分析/写作
local_models:
  orchestrator: qwen2.5:3b          # 调度
  data_local: qwen2.5:7b            # 可选：本地数据解释
serial_loading: true                # 同一时刻只加载一个模型
```

DSH 侧按阶段指定模型：

| 阶段 | 模型 | 工具 |
|---|---|---|
| 数据准备 | `qwen2.5:3b` | `data_*`、`artifact_*` |
| 云端分析 | cloud-large | 只收 `cloud-gate` 允许的产物 |
| 文献综述 | cloud-large | `search_evidence` / `verify_answer` |

## 3. 会话模板

### raw（Excel/CSV/TSV/DOCX）

```
模型：qwen2.5:3b
MCP：仅 scipal-data
流程：
  data_classify(path)
  data_profile(path, project_id)
  data_aggregate(path, project_id, group_by)
  artifact_validate(...)
  cloud_gate(...) → allow=true 后另开会话交给云端
```

### public（论文/摘要）

```
模型：cloud-large
MCP：scipal-search + scipal-data（不需要时可不挂）
流程：search_evidence → 生成 → verify_answer
```

### mixed（原始数据 + 文献）

```
阶段 A（本地）：data_profile / aggregate / sample
阶段 B（云端）：只带 derived 产物 + 公开文献证据
```

## 3.1 会话模板文件

config/dsh_sessions.json 提供 raw / public / mixed 三套模板；也可通过接口获取：

`
POST /api/data/session  {data_class:raw}
→ {models:[local],tools:[...],cloud:false,...}
`

## 4. 环境变量

```
SCIPAL_DATA_ROOT=D:\sciPal\data_sandbox
SCIPAL_MIN_AGG_N=10
SCIPAL_MAX_SAMPLE_ROWS=5
SCIPAL_MODEL_SERIAL=1
SCIPAL_MODEL_LOCK=D:\sciPal\data\model.lock
OLLAMA_HOST=http://127.0.0.1:11434
SCIPAL_ORCHESTRATOR_MODEL=qwen2.5:3b
SCIPAL_API_TOKENS={"tok_local":"default","tok_cloud":"alice"}
```

## 5. 最小操作示例

```text
用户：分析 cohort.xlsx 的 sex × stage 分布，n<10 的组不要给我看

本地 3B：
  data_profile(path="cohort.xlsx", project_id="cohort_2026")
  data_aggregate(group_by=["sex","stage"])
  → artifact agg_ab12cd34（min_cell_n=12）
  artifact_validate → ok
  cloud_gate → allow=true
→ 另开云端会话，只带该聚合表 + 研究问题
```

## 6. 审计与云端交接

`
POST /api/data/cloud-send   # 先 cloud-gate，再写审计
GET  /api/data/audit?project_id=...
`

- 审计只记录 owner/project/artifact/provider/bytes/hash/detail；
- 不记录原始行、文件路径或单元格值；
- cloud_send 是“产物已交给云端”的唯一可信记录。

## 6.1 小模型稳定性实测

`
python scripts/probe_tool_calls.py --model qwen2.5:3b --runs 10
→ single_step 9/10，multi_step true，15.6s
`

失败样例返回空对象，说明需要 schema 校验 + 规则重试。

## 7. 串行模型注意事项

- DSH 侧不要同时触发多个本地模型任务；使用全局队列；
- 每次调用结束可执行 `release_ollama(model)`（Ollama `keep_alive=0`）；
- 8GB 显存下不要同时加载 3B + 7B + embedding；按任务切换；
- 云端不可用时降级为本地摘要，并标注“草稿”。
