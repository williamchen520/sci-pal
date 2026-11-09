# 零技术债 Phase 3s：evidence route PG-only

> 日期：2026-11-09  
> 状态：**/api/evidence/context 的 sentence lookup 不再开 SQLite**

---

## 1. 改动

```text
routes/evidence.py
  sqlite3 删除
  _sentence 默认走 main_read_connection
  新增 sentence_lookup 注入
```

`ContextExpander` 仍由 db_path 构造；生产走 PGReadCompat。

---

## 2. 测试

```text
test_evidence_routes
  传入 SQLite sentence_lookup closure
  测试夹具仍用临时 SQLite
```

结果：

```text
4 passed
```

---

## 3. Allowlist

```text
38 -> 37
```

---

## 4. 说明

路由层不再持有 SQLite；测试保留自己的 fixture。

---

## 5. 下一步

```text
routes/papers.py
routes/review_actions.py
routes/search_downloads.py
routes/system.py
routes/systematic_review.py
routes/papers_actions.py
```
