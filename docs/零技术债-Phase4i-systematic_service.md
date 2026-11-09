# 零技术债 Phase 4i：systematic service 移入 tests

> 日期：2026-11-09  
> 状态：**生产不再 import SQLite systematic service**

---

## 1. 改动

```text
routes/systematic_review.py
  删除 systematic import
  生产只走 pg_systematic / pg_report / pg_pdf
```

```text
services/review/systematic.py
  -> tests/support_sqlite_systematic.py
```

```text
tests/test_systematic_review.py
  改 import support module
```

---

## 2. 验证

```text
systematic service tests   8 passed
```

---

## 3. 说明

route 里 `else systematic.*` 仍未删除，但：

```text
_pg_projects() 恒 True
systematic 已不在命名空间
分支不可达
```

下一轮把它清成纯 PG handler。

---

## 4. Allowlist

```text
24 不变
```

`services/review/systematic.py` 本不在 allowlist（其连接可能由 build_db schema 处理）。
本批主要是切断生产 import。

---

## 5. 下一步

```text
清理 systematic route 不可达分支
```

然后剩余 24 基本都是核心检索和 domain service。
