# 实验记录：RAG 控制面 R6 DSH Tools

> 日期：2026-11-13  
> 状态：**MCP 工具代码/单测完成；DSH 未重启，未 live 调用**  
> 代码：`mcp_server/code_server.py`

---

## 1. 目标

```text
DSH 能提交 RAG 计划
人类审批
DSH 派发已批准计划
DSH 查询 job / query
不暴露 approve
```

## 2. 新增 MCP 工具

```text
rag_plan(intent, steps_json)
rag_plan_status(plan_id)
rag_dispatch(plan_id)
rag_job_status(job_id)
rag_query(capability, library_id, query, top_k)
```

没有：

```text
rag_approve
```

审批只能走人类 Web session：

```text
POST /api/rag/plans/<id>/approve
```

## 3. 配置

```text
SCIPAL_API_URL
SCIPAL_INTERNAL_TOKEN
SCIPAL_API_ENV_FILE
```

`cordis.patch.yml` 增加：

```text
SCIPAL_API_ENV_FILE: G:/sciPal_deploy/deploy/.env
SCIPAL_API_URL: http://127.0.0.1:5001
```

MCP 工具数从 35 增加到 40。

## 4. 测试

```text
tests.test_mcp_rag_tools 3 passed
```

包括：

```text
_api 无 token -> 拒绝
rag_plan 提交 steps
不存在 rag_approve
```

## 5. 未完成

```text
DSH 未重启
没有 live 工具调用
没有在 DSH 里实际 plan -> 人工批准 -> dispatch
```

## 6. 下一步

```text
重启 DSH
在 DSH 中跑一次 rag_plan
人工 Web 审批
rag_dispatch
rag_job_status
```
