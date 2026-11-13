# 实验记录：RAG 控制面 R1 Plans / Jobs / Lease

> 日期：2026-11-13  
> 状态：**R1 队列/审批/租约完成；无 worker 执行器**  
> 代码：`services/rag_control/plans.py`

---

## 1. 目标

```text
Plan 只读提案
人类审批
Dispatch 生成 job
Worker lease/heartbeat
完成写 run
```

## 2. 数据表

```text
rag_plans
rag_plan_steps
rag_jobs
rag_runs
```

状态：

```text
plan  proposed -> approved -> dispatched -> running -> succeeded
job   queued -> leased -> running -> succeeded/failed
```

## 3. API

```text
POST /api/rag/plans
GET  /api/rag/plans/<id>
POST /api/rag/plans/<id>/approve
POST /api/rag/plans/<id>/dispatch
POST /api/rag/plans/<id>/cancel

POST /api/rag/jobs/lease
POST /api/rag/jobs/<id>/heartbeat
POST /api/rag/jobs/<id>/complete
POST /api/rag/jobs/<id>/fail
GET  /api/rag/jobs/<id>
```

## 4. 人工审批

```text
approve 必须有人类 session
带 X-SCIPAL-Internal-Token 的请求被拒绝
plan_hash 必须匹配
审批 1 小时过期
```

## 5. Worker

```text
X-SCIPAL-RAG-Worker-Token
```

lease：

```sql
FOR UPDATE SKIP LOCKED
lease_owner + lease_expires_at
```

## 6. 生命周期 smoke

```text
created    proposed
approved   approved
dispatched queued step
leased     job_d117dae5cfc1
complete   succeeded
final      succeeded
```

## 7. 验证

```text
tests.test_rag_plans 5 passed
tests.test_rag_control 5 passed
validate_arch 224/224 OK
```

## 8. 当前缺口

```text
没有 worker 执行器（R3）
job 只到 leased
没有真正调用 code_rag.ingest
没有 evidence/artifact
没有 DSH rag_plan 工具
```

## 9. 下一步 R2/R3

```text
R2 model registry + index binding
R3 local worker + code ingest
```

R1 只证明“计划、审批、派发、租约、完成”状态机可用。
