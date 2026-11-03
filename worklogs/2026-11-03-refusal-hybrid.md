# Worklog: 长查询 sufficiency 回退

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

#272 的单条覆盖率修复了 q023/q025，但 96 题 recall 从 0.6615 降到 0.6302，q051/q070/q089 被误拒。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
services/qa/sufficiency.py
tests/test_sufficiency.py
worklogs/2026-11-03-refusal-hybrid.md
docs/Research_Logs_Index.md
```

## 4. 业务逻辑变化

```text
<=3 个内容词：仍用最高分证据的单条覆盖率（严格）
>=4 个内容词：用整个结果集的并集覆盖率（宽松）
分数门槛 min_score 不变
```

原因：

```text
q051/q070/q089 的答案分散在多段
短查询 q023/q025 必须由单条强证据覆盖
```

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
tests.test_sufficiency
9 tests OK

python -m unittest discover -s tests -p "test_*.py"
814 tests OK
```

真实请求验证：

```text
q023 False
q025 False
q051 True
q070 True
q089 True
```

## 7. 风险 / 外部 API

```text
无新增外部 API
无数据库写入
无鉴权变化
长查询仍可能有域外误答；完整 96 题需部署后复跑
```

## 8. 未完成项

```text
PR Pending Review
部署后复跑完整 96 题
```
