# 实验记录：R6 DSH Live 验收

> 日期：2026-11-13  
> 状态：**DSH 工具 live 通过；query plan 执行未通过**
> 环境：DSH 重启后 40 个 MCP 工具

---

## 1. 结果

### rag_plan

创建：

```text
plan_318a284a1fd6
status proposed
plan_hash 1e3f85b0...
```

### 未批准 dispatch

```text
rag_dispatch
-> SciPal API rejected: {"error":"plan is proposed"}
```

审批门有效。

### 人工批准

使用本地 `ui_admin` session：

```text
approved_by user_06341395d1d84f18be68883f22d36705
```

### rag_dispatch

```text
status dispatched
step queued
job job_0c426073e0bf
```

### rag_job_status

```text
status queued
job_type rag_query
attempts 0
```

### rag_query

真实 code RAG：

```text
run qry_b24eaaad25da
results 2
evidence ev_1732cc6c5851
evidence ev_75c55bbd8327
top1 normalize_total
path src/scanpy/preprocessing/_normalization.py:136-315
```

### rag_plan_status

```text
status dispatched
step queued
```

## 2. 发现的问题

```text
rag_query plan 可以 dispatch 成 job
但没有 worker 执行 rag_query
job 永远 queued
```

当前 worker 只支持：

```text
rag_ingest
```

所以：

```text
rag_plan(rag_query) -> dispatch -> queued = 未完成
```

不能把 dispatched 当 executed。

## 3. 清理

```text
测试 plan/job 已删除
query run/evidence 保留为真实查询记录
```

## 4. 结论

```text
DSH -> plan -> 审批 -> dispatch     PASS
DSH -> query -> evidence            PASS
DSH -> query plan -> executed       NOT IMPLEMENTED
```

## 5. 下一步

```text
1. rag_query job worker
   或 gateway 直接把 query plan 当同步查询执行
2. 计划审批 UI
3. 多 RAG 路由
```
