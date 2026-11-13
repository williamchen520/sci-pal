# 实验记录：R6.1 Query Worker

> 日期：2026-11-13  
> 状态：**query plan 端到端通过**  
> 代码：`scripts/rag_worker.py`、`services/rag_control/plans.py`

---

## 1. 问题

R6 live 暴露：

```text
rag_query plan -> dispatch -> job queued
worker 只支持 rag_ingest
job 永远不执行
```

## 2. 修复

worker 增加 `rag_query` 分支：

```text
POST code API /libraries/<id>/search
  -> 构造 evidence
  -> complete(job) 同时写 run + evidence
```

`complete_job` 增加 `evidence` 参数，run/evidence/job 在同一事务提交。

## 3. E2E

Plan：

```text
plan_c898a05608e8
```

Job：

```text
job_494df5a24f62
```

结果：

```text
plan      succeeded
job       succeeded
run       run_ce098d33b719
hits      2
evidence  2
```

Evidence 路径：

```text
src/scanpy/preprocessing/_normalization.py
```

## 4. 验证

```text
tests.test_rag_query_worker 1 passed
tests.test_rag_worker       2 passed
tests.test_rag_plans        5 passed
```

## 5. 清理

测试 plan/run 已删除；live query `qry_b24eaaad25da` 保留。

## 6. 结论

```text
rag_query job -> executed -> evidence   PASS
```

现在 `rag_query` 不再是“dispatch 完就卡住”。

## 7. 下一步

```text
计划审批 UI
多 RAG 路由
```
