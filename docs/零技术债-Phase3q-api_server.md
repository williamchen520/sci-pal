# 零技术债 Phase 3q：api_server 启动 SQLite 清理

> 日期：2026-11-09  
> 状态：**run_db_migrations / stale task reconcile 不再碰 SQLite**

---

## 1. 改动

```text
api_server.py
  run_db_migrations() -> no-op
  reconcile_stale_review_tasks() -> 0
  sqlite3 启动连接删除
```

---

## 2. 原因

```text
research.db 已归档
SQLite 自动迁移无对象
review task 恢复已由 PGTaskManager.recover_stale_tasks()
```

---

## 3. 验证

```text
py_compile api_server   OK
allowlist               40 -> 39
```

---

## 4. 下一步

```text
routes/abstracts.py
routes/evidence.py
routes/papers.py
...
```

按路由逐个判断。
