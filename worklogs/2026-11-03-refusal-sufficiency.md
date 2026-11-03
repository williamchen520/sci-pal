# Worklog: 域外拒答回归修复

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

`SCIPAL_CONTEXTUAL_MODE=always` 后，96 题 refusal 从 0.75 降到 0.50；q023（汞沸点）和 q025（法国首都）被误判为 sufficient。

## 2. ARCHITECTURE.json 变化

```text
无
```

本 PR 不修改 JSON，无路由变化。

## 3. 修改文件

```text
services/qa/sufficiency.py
services/qa/qa_service.py
tests/test_sufficiency.py
worklogs/2026-11-03-refusal-sufficiency.md
docs/Research_Logs_Index.md
```

## 4. 业务逻辑变化

```text
sufficiency 从“整个结果集的 token 并集”改为“最高分证据的单条覆盖率”
查询越短要求越高：
  <=2 个内容词 -> 1.0
  3 个         -> 0.6
  4 个         -> 0.5
  >=5 个       -> 0.25
qa_service 不再用 domain refusal_threshold 二次覆盖 sufficiency 结论
```

原因：

```text
并集会让 10 篇无关文档凑出 100% 覆盖率
q023 的 top 证据只覆盖 1/3；q025 的 top 证据只覆盖 1/2
```

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
python -m unittest tests.test_sufficiency
8 tests OK

python -m unittest discover -s tests -p "test_*.py"
813 tests OK
```

离线验证：

```text
q023 sufficient=False top_item_coverage=0.3333 min=0.6
q025 sufficient=False top_item_coverage=0.5 min=1.0
20 道有答案题：20/20 sufficient=True
```

## 7. 风险 / 外部 API

```text
无新增外部 API
无数据库写入
无鉴权变化
短查询拒答更保守；长查询阈值降低
完整 96 题需部署后复跑确认
```

## 8. 未完成项

```text
PR Pending Review
部署后复跑完整 96 题
```
