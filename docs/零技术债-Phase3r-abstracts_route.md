# 零技术债 Phase 3r：abstracts route PG-only

> 日期：2026-11-09  
> 状态：**/api/abstracts 删除 SQLite fallback**

---

## 1. 改动

```text
routes/abstracts.py
  sqlite3 / abstracts.db / _pg_enabled 删除
  /abstracts/list、/abstracts/<pmid> 固定 PG
```

`db_path` 保留兼容但忽略。

---

## 2. 测试

```text
test_abstracts_routes.py
  旧：临时 SQLite papers 表
  新：fake PG
```

结果：

```text
4 passed
```

---

## 3. Allowlist

```text
39 -> 38
```

---

## 4. 下一步

```text
routes/evidence.py
routes/papers.py
routes/review_actions.py
routes/search_downloads.py
routes/system.py
routes/systematic_review.py
routes/papers_actions.py
```
