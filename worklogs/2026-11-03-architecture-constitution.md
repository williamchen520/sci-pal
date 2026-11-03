# Worklog: ARCHITECTURE.json 只读与审批

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

把 `ARCHITECTURE.json` 定为只读宪法；修改需人类批准；增加提交拦截钩子。

## 2. ARCHITECTURE.json 变化

```text
无
```

本 PR 不修改 JSON。

## 3. 修改文件

```text
.dsh_rules
AGENTS.md
CONTRIBUTING.md
CONTRIBUTING.zh-CN.md
.github/pull_request_template.md
docs/开发流程规范.md
README.md
README.zh-CN.md
.githooks/pre-commit
.githooks/commit-msg
worklogs/2026-11-03-architecture-constitution.md
```

## 4. 业务逻辑变化

```text
无 Python 逻辑变化
新增 Git 钩子：
  pre-commit  检查 staged JSON + JSON 合法性
  commit-msg  JSON 变更必须含 [APPROVED_BY_HUMAN]
```

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
python -m unittest discover -s tests -p "test_*.py"
809 tests OK
```

钩子临时仓库测试：

```text
无标签 commit -> exit 1
有 [APPROVED_BY_HUMAN] -> commit 成功
```

## 7. 风险 / 外部 API

```text
无新增外部 API
无数据库写入
无鉴权代码变化
钩子可被 --no-verify 绕过（本地防误操作，不是服务器强制）
```

## 8. 未完成项

```text
等待人工“批准合并”
```
