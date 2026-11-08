# 零技术债 Phase 3f：退役 health-cron / dual_write

> 日期：2026-11-09  
> 状态：**health-cron 已移除；dual_write outbox 体系删除**

---

## 1. 删除服务

```text
health-cron
```

原因：

```text
PG-only 后没有 SQLite outbox 需要健康检查
```

compose 已删除该 service。

---

## 2. 删除模块

```text
services/db/dual_write.py
```

同步删除：

```text
scripts/dual_write_healthcheck.py
scripts/g3_outbox_gate.py
scripts/p4_staging_soak.py
scripts/replay_dual_write.py
scripts/setup_dual_write.py
scripts/pg_write_health.py
scripts/remove_tenancy_outbox.py
scripts/retire_claims_reviews_outbox.py
scripts/retire_watch_outbox.py
```

测试：

```text
test_dual_write
test_dual_write_health
test_remove_tenancy_outbox
test_retire_claims_reviews_outbox
test_retire_watch_outbox
```

---

## 3. 保留 etl

```text
services/db/etl.py
```

仍被离线脚本使用：

```text
create_pg_v2
fts_alignment
rebuild_fts_porter
```

所以本轮不删 etl，避免打断历史工具。

---

## 4. 验证

```text
pg_etl / read_router   9 passed
```

---

## 5. 当前

```text
运行时 SQLite 硬禁
health-cron 退役
dual_write 删除
etl 保留为离线
allowlist 50
```

---

## 6. 剩余

```text
services/db/etl.py
50 个 connect 文件
```

下一步：

```text
继续清离线/审计模块
etl 最后再处理
```
