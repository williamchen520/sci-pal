# AGENTS.md — mixed 会话（本地准备 → 云端综合）

> 工作区模板：先本地处理原始数据，再把聚合/脱敏产物交给云端模型。

## 阶段 A（本地，raw）

1. `open_session("raw")`；
2. `data_profile` / `data_aggregate` / `data_sample`；
3. `artifact_validate`；
4. `cloud_gate(provider="deepseek")`，记录返回的 `artifact_id`。

## 阶段 B（云端，public）

1. 只带阶段 A 的 `artifact_id` 与聚合结果，不带原始文件路径/原始行；
2. `search_evidence` 补充公开文献；
3. 生成后 `verify_answer`；
4. `cloud_send(artifact_id, provider="deepseek")` 记录交接。

## 禁止

- 在阶段 B 读取原始 xlsx/csv/tsv/docx；
- 把未过 `cloud_gate` 的产物发给云端；
- 在阶段 A 调用云端工具。
