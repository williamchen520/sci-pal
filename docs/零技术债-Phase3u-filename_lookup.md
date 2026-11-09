# 零技术债 Phase 3u：papers filename lookup

> 日期：2026-11-09  
> 状态：**review_actions / search_downloads 的 filename lookup 改 PG**

---

## 1. 新 helper

```text
services/papers/lookup.py
  find_parsed_paper(filename)
  public.papers
  ORDER BY total_paragraphs DESC NULLS LAST, created_at ASC
```

---

## 2. 路由

```text
routes/review_actions.py
routes/search_downloads.py
```

删除各自 SQLite `_find_parsed_paper`，改调用共享 helper。

```text
routes/papers_actions.py
  增加 lookup 注入
  默认调用共享 helper
```

---

## 3. 测试

```text
test_papers_downloads_routes
  注入 SQLite lookup closure
```

---

## 4. 验证

```text
papers downloads / review actions   15 passed
allowlist                            36 -> 34
```

---

## 5. 下一步

```text
routes/system.py
routes/systematic_review.py
routes/papers_actions.py（还剩多处 SQLite）
```
