# 零技术债 Phase 3o：notes service PG-only

> 日期：2026-11-09  
> 状态：**生产 notes service 固定 PG；SQLite 移入 tests**

---

## 1. 生产

```text
services/notes/service.py
  sqlite3 / SCHEMA / _connect / paper_in_workspace 删除
  list/create/update/delete 固定 pg_service
  db_path 保留兼容
```

---

## 2. 测试

```text
tests/support_sqlite_notes.py
  旧的 SQLite notes 实现
```

`routes/notes.py` 增加：

```text
service=None
```

默认生产 service；测试传 SQLite 模块。

`test_notes_routes` 改用 support module。

---

## 3. 验证

```text
notes routes + notes pg   8 passed
allowlist                 42 -> 41
```

---

## 4. 下一步

```text
claims/service
```

同样的 pattern：生产 PG，SQLite 移入 tests，路由注入。
