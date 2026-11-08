# 零技术债 Phase 3e：batch 3

> 日期：2026-11-08  
> 状态：**DB 兼容层三个模块删除；dual_write 暂留**

---

## 1. 删除

```text
services/db/adapter.py
services/db/shadow_read.py
services/db/sqlite_readonly.py
```

同步删除：

```text
tests/test_db_adapter.py
tests/test_shadow_read.py
tests/test_sqlite_readonly.py
scripts/p3_shadow_report.py
scripts/shadow_read.py
```

清理：

```text
services/db/__init__.py 导出
```

---

## 2. 为什么不是四个

`services/db/dual_write.py` 仍被：

```text
health-cron -> scripts/dual_write_healthcheck.py
```

使用。

删它必须先停/替换 health-cron，不能混在本次 batch。

---

## 3. Allowlist

```text
52 -> 50
SQLITE_ALLOWLIST_OK 50
```

---

## 4. 测试

```text
read_router / pg_etl / dual_write   14 passed
sqlite group                        37 passed
```

---

## 5. 下一步

```text
1. 决定 health-cron 是否保留
2. 若删除：dual_write + etl 一起清
3. 否则保留 dual_write，继续别的模块
```

这是第一次 batch 不足四个：

```text
不是漏做
是 dual_write 有生产 cron 依赖
```
