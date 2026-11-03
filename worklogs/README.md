# Worklogs

每个完成的施工任务写一个文件：

```text
worklogs/YYYY-MM-DD-<topic>.md
```

模板：

```text
# Worklog: <topic>

## 1. 需求
## 2. ARCHITECTURE.json 变化
## 3. 修改文件
## 4. 业务逻辑变化
## 5. validate_arch 结果
## 6. 测试命令与通过率
## 7. 风险 / 外部 API
## 8. 未完成项
```

规则：

```text
测试全绿后才写 Worklog
Worklog 与代码在同一个 PR
PR 状态 Pending Review
只有人类回复“批准合并”才能 merge
```
