# 实验记录：RAG 控制面 R5 Gateway Query

> 日期：2026-11-13  
> 状态：**code_search 真实网关 + evidence 通过；DSH 工具未接**  
> 代码：`services/rag_control/gateway.py`

---

## 1. 目标

```text
POST /api/rag/query
  -> code RAG
  -> query run
  -> evidence ledger
```

只实现 `code_search`，不伪造文献/文档路由。

## 2. API

```text
POST /api/rag/query
{
  "capability": "code_search",
  "library_id": "lib_2c...",
  "query": "normalize_total",
  "top_k": 10
}
```

失败：

```text
unsupported capability -> 400
code RAG unavailable    -> 400
```

## 3. 真实结果

```text
run qry_686112051c2f
results 2
first normalize_total
evidence 2
```

每条 hit 写：

```text
source_path
start_line / end_line
content_hash (snippet sha256)
score
metadata.unit_id / symbol_name / unit_type
```

## 4. 数据

query run：

```text
rag_runs.run_type = query
job_id = NULL
```

`rag_runs.job_id` 改为可空；查询不需要 dispatch。

## 5. 验证

```text
tests.test_rag_gateway 3 passed
tests.test_rag_ledger  3 passed
validate_arch 233/233 OK
```

## 6. 边界

```text
只支持 code_search
没有 literature/docs gateway
没有 DSH rag_plan 工具
没有计划级审批（只读查询）
```

## 7. 下一步 R6

```text
DSH rag_plan / rag_dispatch 工具
多 RAG 路由
审批闭环
```
