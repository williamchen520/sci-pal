# P4h 测试后端分组结果

> 日期：2026-11-08  
> 状态：**SQLite / PG 测试已分开跑**

---

## 1. 分组

```text
--group sqlite
  test_review_repository
  test_reviews_routes
  test_systematic_review
  test_tasks_routes

--group pg
  test_pg_pool
  test_pg_schema_v2
  test_db_writer_pg_only
  test_task_lookup
  test_pg_fts
  test_pg_vector
  test_pg_paragraph_retriever
  test_claims_pg_read
  test_projects_pg
  test_tenancy_pg_writes
  test_watch_pg_store
```

---

## 2. 结果

```text
sqlite    25 passed
pg        41 passed
```

---

## 3. 用法

```bash
python scripts/run_tests_guarded.py --group sqlite
SCIPAL_PG_DSN=... python scripts/run_tests_guarded.py --group pg
```

分组时 runner 会清理：

```text
SCIPAL_REVIEWS_BACKEND
SCIPAL_PROJECTS_BACKEND
SCIPAL_EXPERIMENTS_BACKEND
SCIPAL_CLAIMS_BACKEND
SCIPAL_TASKS_BACKEND
SCIPAL_SYSTEMATIC_BACKEND
SCIPAL_WATCH_PG_STORE
```

PG 组再统一设置 `postgres`。

---

## 4. 结果

```text
全局 PG backend 不再污染 SQLite 断言
```

预期日志：

```text
PG tenancy create_user failed; refusing SQLite fallback: pg down
```

这是负路径测试，不是故障。

---

## 5. 下一步

```text
1. 把更多测试文件纳入分组
2. 跑全量
3. public 对 admin 只读的最终评估
```
