# 实验记录：Replication Plan

> 日期：2026-11-14  
> 状态：只生成计划，不执行  
> 目标：把 module + data flow 变成可审查的复刻步骤

---

## 1. API

```text
POST /api/papers/<paper_id>/replication-plan
{"target": "Figure.1.R"}
```

## 2. 逻辑

```text
paper_modules(paper_id)
  -> target file
paper_data_flow(paper_id)
  -> reads / writes
```

输出：

```text
status planned
language
inputs
outputs
steps
tests []
risks
executed false
```

## 3. HCC 实测

```text
target  Figure.1.R
status  planned
inputs  []
outputs Total single-cell atlas.rds
        Our single-cell atlas.rds
executed false
```

Figure.1 的输入来自内存中的 75 个样本对象，不是文件，所以 inputs 为空是正确结果。

## 4. 边界

```text
不执行 R
不下载数据
不生成测试
没有测试不能标 verified
仓库无 LICENSE 是风险
```

## 5. MCP

`scipal-paper` 第 10 个工具：

```text
paper_replication_plan(paper_id, target)
```

## 6. 测试

```text
planned
missing target -> blocked
unbound -> blocked
```

```text
test_paper_replication 3 passed
```

## 7. 路由

```text
json_routes=267
app_routes=267
OK
```

## 8. 下一步

```text
1. 重启 app/DSH
2. 端到端 MCP paper_replication_plan
3. 真执行需 sandbox + 人工批准
```
