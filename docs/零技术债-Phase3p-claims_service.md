# 零技术债 Phase 3p：claims service PG-only

> 日期：2026-11-09  
> 状态：**生产 claims service 固定 PG；SQLite 移入 tests**

---

## 1. 生产

```text
services/claims/service.py
  sqlite3 / schema / FTS / SQLite CRUD 删除
  改为 PG facade
```

委托：

```text
pg_read.list_claims / get_claim
pg_search.search_candidates / interrogate
pg_write.add_evidence / decide / add_note
pg_writes.create_claim / update_claim
```

`connect()` 返回 None，仅兼容路由 fallback 签名。

---

## 2. 测试

```text
tests/support_sqlite_claims.py
  原 SQLite service
```

`test_claim_pilot` 改用 helper，并注入：

```text
build_claims_blueprint(..., service=support_sqlite_claims)
```

`routes/claims.py` 增加 `service` 参数，默认生产模块。

---

## 3. 循环依赖修复

`pg_write` 反向 import `service` 常量，因此把 pg 模块 import 延迟到函数内部。

---

## 4. 验证

```text
claim pilot / claims pg / claims   15 passed
allowlist                          41 -> 40
```

---

## 5. 专项 1 收口

```text
notes/service       完成
review_repository   完成
references/library  完成
claims/service      完成
```

---

## 6. 剩余

```text
核心检索 fallback
routes 层 fallback
tenancy 边界
```
