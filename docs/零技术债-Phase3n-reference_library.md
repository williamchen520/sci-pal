# 零技术债 Phase 3n：reference library PG-only

> 日期：2026-11-09  
> 状态：**生产 ReferenceLibrary 固定 PG；SQLite 移入 tests**

---

## 1. 生产

```text
services/references/library.py
  sqlite3 / SCHEMA / _session / _connect 删除
  import_references / list / count 固定 _pg()
  ensure_schema no-op
  db_path 保留兼容
```

---

## 2. 测试

```text
tests/support_sqlite_reference_library.py
  SqliteReferenceLibrary
```

`test_references_interchange` 改用 helper。

路由本来就注入：

```text
build_references_blueprint(get_library=...)
```

因此无需改路由签名。

---

## 3. 验证

```text
references interchange   11 passed
allowlist                43 -> 42
```

---

## 4. 下一步

```text
剩余 A 类里可独立收敛的继续
review_repository / references/library 模板已成立
```
