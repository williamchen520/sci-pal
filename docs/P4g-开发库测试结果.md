# P4g 开发库测试结果

> 日期：2026-11-08  
> 状态：**开发库可用；测试环境需按后端分组**

---

## 1. 通过

```text
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

合计：

```text
31 + 10 = 41 passed
```

---

## 2. 失败原因

运行：

```text
test_review_repository
test_reviews_routes
test_systematic_review
test_tasks_routes
```

出现 5 个失败，原因是：

```text
环境设置 SCIPAL_REVIEWS_BACKEND=postgres
但测试用例用 SQLite 临时库断言 schema
```

切回 SQLite backend 后：

```text
test_review_repository
test_reviews_routes
13 passed
```

不是代码回归，是测试后端选择冲突。

---

## 3. 兼容修复

`claims/experiments/watch pg_read` 增加：

```text
pg_connection = main_read_connection
```

保留旧测试的 mock 接口。

---

## 4. 结论

```text
scipal_dev 可用于 PG 数据层测试
SQLite 单测必须显式关闭 PG backend
```

测试运行器应按测试文件设置后端，而不是全局 `.env`。

---

## 5. 下一步

```text
1. 给 test runner 加 backend 分组
2. 再用 scipal_dev 跑全量
3. public 对 admin 只读的最终评估
```
