# 全站端点分层烟测：A 组结果

> 日期：2026-11-08  
> 环境：生产容器、无 research.db、PG-only

## 结果

```text
tested  31
5xx     0
```

## 通过

```text
/api/health
/api/abstracts/list
/api/papers
/api/papers/<id>
/api/papers/<id>/graph
/api/papers/local
/api/projects
/api/projects/<id>
/api/projects/<id>/experiments
/api/experiments
/api/experiments/<id>
/api/experiments/<id>/runs
/api/claims
/api/claims/<id>
/api/claims/<id>/events
/api/notes
/api/watch/profiles
/api/tasks
/api/workspaces
/api/workspaces/<id>/members
/api/domain-packs
/api/guard/stats
/api/references
/api/protocols
/api/protocols/<id>
/api/reviews
/api/reviews/<id>
/api/review-projects
/api/review-projects/<id>
/api/qa/status
/api/review/llm_status
```

## 404（预期）

```text
/api/abstracts/<paper_id>
  paper_id 不是 pmid

/api/papers/<paper_id>/trace
  sentence_id 与 paper_id 不匹配
```

## 修复

```text
references ensure_schema  PG 下跳过
reviews ensure_schema     PG 下跳过
tasks list/get            接 PG
SCIPAL_TASKS_BACKEND=postgres
```

## 结论

```text
A 组通过
无 5xx
```

B/C 组仍待执行。
