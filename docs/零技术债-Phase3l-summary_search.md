# 零技术债 Phase 3l：summary_search PG-only

> 日期：2026-11-09  
> 状态：**SummarySearch SQLite fallback 删除**

---

## 1. 改动

```text
services/search/summary_search.py
  sqlite3 / summaries_fts / DEFAULT_DB 删除
  SCIPAL_SEARCH_META_BACKEND 分支删除
  查询固定走 public.summaries + PG FTS
```

`db_path` 保留兼容但忽略。

---

## 2. 测试

```text
test_build
  只断言 build 统计

test_search_uses_postgres
  fake PG 返回 p1

test_no_terms
  不再 build SQLite
```

结果：

```text
4 passed
```

---

## 3. Allowlist

```text
45 -> 44
```

---

## 4. 说明

`build_db/build_summaries.py` 仍是离线 builder；本次只清运行时读取路径。

---

## 5. 下一步

```text
review_repository
references/library
```
