# 实验记录：Paper Analysis 聚合入口

> 日期：2026-11-14  
> 状态：`scipal-paper` 后端聚合入口；代码层未接  
> 目标：一次调用返回单篇论文的结构、首段和证据

---

## 1. 新增

```text
services/papers/analysis.py
GET /api/papers/<paper_id>/analysis?q=...&top_k=8
```

返回：

```text
paper
outline / outline_summary
first_paragraph
evidence
data_flow
code
status
gaps
```

compact 模式：

```text
outline=[]
outline_summary.by_type
data_flow.nodes_count
data_flow.edges_count
```

MCP 默认 `compact=true`。

## 2. 用途

`scipal-paper` 不需要先调 4 个接口：

```text
outline
first paragraph
evidence
metadata
```

一次拿齐。

## 3. 边界

```text
code link / module map / data flow 还没接
只返回 not_indexed，不伪造
evidence 为空时 status=partial
```

## 4. 验证

```text
compact=True
  outline=[]
  section_count=43
  by_type={results:8, methods:21, ...}
  flow nodes=16 / edges=16

json_routes=268
app_routes=268
OK
```

```text
test_paper_analysis  2 passed
test_paper_evidence  3 passed
test_paper_reader    4 passed
合计                 9 passed
```

## 5. 下一步

```text
1. app 重启验证 /analysis
2. paper_code_links
3. module map
4. scipal-paper MCP 转发
```
