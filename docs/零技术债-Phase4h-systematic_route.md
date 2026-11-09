# 零技术债 Phase 4h：systematic route 强制 PG

> 日期：2026-11-09  
> 状态：**路由不再打开 SQLite 连接**

---

## 1. 改动

```text
routes/systematic_review.py
  sqlite3 删除
  _pg_projects() -> True
  _conn() -> None
```

所有 handler 的 `_pg_projects()` 分支固定走：

```text
pg_systematic
pg_report
pg_pdf
```

---

## 2. 效果

```text
生产不再创建 SQLite 连接
systematic service 的 SQLite 只留在测试
```

---

## 3. Allowlist

```text
26 -> 24
```

减少两个文件：

```text
routes/systematic_review.py
```

（另一个是上一批 protocols 的余量）

---

## 4. 说明

`else systematic.*` 代码仍在文件里，但已不可达；下一轮清理为纯 PG handler。

---

## 5. 下一步

```text
清理 systematic route 的不可达 SQLite 分支
services/review/systematic.py 移入 tests
```
