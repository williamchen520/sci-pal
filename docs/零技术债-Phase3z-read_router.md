# 零技术债 Phase 3z：ReadRouter PG-only

> 日期：2026-11-09  
> 状态：**read_router 删除 SQLite fallback**

---

## 1. 改动

```text
services/db/read_router.py
  sqlite3 / _sqlite_rows 删除
  should_use_pg 恒 True
  list_papers 直接 PG，失败返回 error 不再 fallback
  paper_detail 直接 PG
```

`sqlite_path` / canary_percent 保留兼容参数。

---

## 2. 测试

```text
test_read_router
  旧：SQLite canary=0 / PG error fallback
  新：PG 正常 / PG error 返回 error / detail PG
```

结果：

```text
read_router + papers routes   9 passed
```

---

## 3. Allowlist

```text
32 -> 31
```

---

## 4. 行为

```text
读取不再有 SQLite 安全网
PG 失败由调用方决定 503
```

papers 路由已按此实现。

---

## 5. 下一步

```text
services/experiments/service.py
services/projects/service.py
services/protocols/service.py
```

继续 domain service 迁移。
