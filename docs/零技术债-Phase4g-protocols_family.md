# 零技术债 Phase 4g：protocols family 收口

> 日期：2026-11-09  
> 状态：**route 单一 service 接口；生产 PG；SQLite service 移入 tests**

---

## 1. 生产

```text
services/protocols/pg_service.py
  PGProtocolService
    import / list / count / get
    runs / attachments / export
```

```text
api_server.get_protocol_service()
  返回 PGProtocolService
```

```text
routes/protocols.py
  删除 _pg_read / pg_* fallback
  只调用 get_service()
```

```text
services/protocols/helpers.py
  纯解析/格式化 helpers
```

---

## 2. 测试

```text
tests/support_sqlite_protocol_service.py
  原 ProtocolService
```

测试改用 helper；route 测试继续用 FakeService。

---

## 3. 验证

```text
protocols / from_review / pg_import / pg_read   30 passed
allowlist                                       26 -> 25
```

---

## 4. 行为

```text
生产不再有 route 双路径
PG 失败由 service / route 返回错误
```

---

## 5. 下一步

```text
routes/systematic_review.py
```

systematic family 收口。
