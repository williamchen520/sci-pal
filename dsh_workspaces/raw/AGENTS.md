# AGENTS.md — raw 数据会话（本地）

> 工作区模板：只把本目录当作会话 workspace 打开；模型选择本地 `qwen2.5:3b`（若 DSH 提供选择器）。

## 铁律

1. 原始数据（xlsx/csv/tsv/docx）**只在本地处理**，禁止上传云端。
2. 只使用 `scipal-data` 工具：`open_session`、`data_classify`、`data_profile`、`data_aggregate`、`data_sample`、`artifact_*`、`cloud_gate`、`cloud_send`。
3. 不要调用 `search_evidence`、`ask_question`、`generate_review` 等云端/文献工具。
4. 聚合与样例必须满足 `n ≥ 10`；小格自动抑制，不要尝试恢复。
5. 需要云端分析时：先 `artifact_validate`，再 `cloud_gate`，`allow=true` 后另开 public/mixed 会话。
6. 产出物落在 `data_sandbox/<owner>/<project>/`，不要直接修改原始文件。

## 推荐流程

```text
open_session("raw")
data_classify(path)
data_profile(path, project_id)
data_aggregate(path, project_id, group_by=[...])
artifact_validate(artifact_id, project_id)
cloud_gate(artifact_id, project_id, provider="deepseek")
→ allow=true 后，把产物 id 带到云端会话
```

## 失败处理

- 工具参数不合法：重试一次；仍失败则改用 `data_profile` 的最小参数。
- `cloud_gate` 拒绝：不要绕过；把 `reasons` 原样告诉用户。
