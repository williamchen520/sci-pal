# 零技术债 Phase 3v：papers_actions paper store

> 日期：2026-11-09  
> 状态：**paper existence/filename/workspace 已走 PaperStore**

---

## 1. 新增

```text
services/papers/paper_store.py
  PaperStore.exists
  PaperStore.filename
  PaperStore.in_workspace
```

生产固定 PG。

---

## 2. 路由

```text
routes/papers_actions.py
  _paper_exists   -> store.exists
  _paper_filename -> store.filename
  before_request  -> store.in_workspace
  新增 paper_store 注入
```

---

## 3. 测试

```text
tests/support_sqlite_paper_store.py
  SqlitePaperStore
```

注入到：

```text
test_papers_downloads_routes
test_pdf_signed
test_trace_routes
```

结果：

```text
16 passed
```

---

## 4. Allowlist

```text
仍为 34
```

原因：

```text
allowlist 统计“文件”，不是“connect 数”
papers_actions.py 还剩 6 处 connect
只有全部清掉，文件才会退出 allowlist
```

---

## 5. 下一步

继续清 `papers_actions` 剩余 6 处：

```text
supplementary_counts
list_local_papers
parse sync
trace payload
render filename
assign workspace
```
