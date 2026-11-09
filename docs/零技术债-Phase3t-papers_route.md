# 零技术债 Phase 3t：papers route PG-only

> 日期：2026-11-09  
> 状态：**/api/papers 与 /api/papers/<id> 不再回退 SQLite**

---

## 1. 改动

```text
routes/papers.py
  sqlite3 / ensure_workspace_scoping 删除
  list/detail 固定 PG ReadRouter
  PG 失败 -> 503，不再 fallback SQLite
  新增 router_factory / detail_router_factory 注入
```

`paper_graph` 逻辑未动。

---

## 2. 测试

```text
test_papers_routes
  FakeRouter 返回 postgres 结果
  列表 / 详情 / 404 / graph 全部覆盖
```

结果：

```text
6 passed
```

---

## 3. Allowlist

```text
38 -> 36
```

---

## 4. 行为变化

```text
PG 读失败不再静默降级 SQLite
改为 503 paper read backend unavailable
```

这是有意的：runtime guard 下 SQLite fallback 本来就不可用。

---

## 5. 下一步

```text
routes/review_actions.py
routes/search_downloads.py
routes/system.py
routes/systematic_review.py
routes/papers_actions.py
```
