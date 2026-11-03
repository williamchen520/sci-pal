# PostgreSQL 迁移最终验收

> 日期：2026-11-03  
> 代码基线：`9443c06`  
> 目标库：`scipal_bench`  
> 结论：**有条件通过，不能标记 P6 完成**

---

## 1. 执行摘要

```text
P0 备份/冻结        部分完成
P1 Schema/连接层    已完成
P2 只读 ETL         已完成
P3 影子读           代码完成，未持续运行
P4 双写             PG-primary + SQLite mirror/outbox，未关闭
P5 读切换           papers 读 100% PG，但有 SQLite fallback
P6 归档             未完成
```

关键判断：

```text
运行时已经不是“SQLite 单轨”
但也不是“PG 单轨”
当前是 PG-primary + SQLite mirror/fallback 的混合态
```

---

## 2. P0：备份机制

### 2.1 已有脚本

```text
scripts/backup_sqlite.py   VACUUM INTO + integrity_check + sha256
deploy/backup.py           SQLite online backup + data tar.gz
deploy/backup.ps1          Windows 包装
deploy/backup.sh           Linux 包装
```

### 2.2 已验证快照

```text
snapshot  D:\sciPal\backups\research_20261031_210616.db
integrity ok
papers    3310
sha256    37e328a8a40edf5e1f25f1dcd72af80bdfdbbcfa4f7796e13d803aa5762fc607
```

与 `docs/PostgreSQL迁移-基线.md` 记录一致。

`deploy/backup.py` 临时库测试：

```text
archive 可生成
包含 data/research.db
包含 data/x.txt
```

### 2.3 发现的问题

```text
1. ~~deploy/backup.py 的 tar 包中 data/research.db 出现两次~~
   已在本轮修复，并加了回归测试
2. ~~没有自动定时备份~~：`backup-cron` 已部署并完成首次备份
3. 没有定期恢复演练记录
4. G 盘最新业务快照仍是 2026-11-02 的 before-tenancy
5. 没有 30 天保留策略的实际执行证据
```

首次自动备份：

```text
archive   scipal-20261103-110222.tar.gz
size      3,557,726,245 bytes (3.56 GB)
integrity ok
papers    3313
status    backups/backup_status.json
```

结论：

```text
脚本化：是
单次可用：是
自动定时：已部署，首次成功
恢复演练：脚本已做 integrity/papers 验证，未做持久化恢复
P0 仍不能签字：30 天保留与异地备份未解决
```

容量问题与策略：

```text
首版全量 archive 3.56 GB/天
30 天约 107 GB，G 盘约 53 GB，不可持续

已改为：
  每日 DB 快照（scipal-db-*）
  每周全量 data（scipal-full-*）
  DB 保留 30 天
  全量保留 28 天
```

---

## 3. P1 / P2 / P3

### P1 Schema / 连接层

```text
build_db/postgres_schema.sql
build_db/postgres_schema_v2.sql
services/db/adapter.py
```

已有 PG adapter、schema、连接测试，P1 完成。

### P2 只读 ETL

```text
services/db/etl.py
scripts/pg_etl.py
```

有 dry-run / checksum / verify 结果，P2 完成。

### P3 影子读

```text
services/db/shadow_read.py
docs/PostgreSQL迁移-P3-shadow.json
```

代码和一次性报告存在，但没有形成每日/每周持续影子读。

结论：

```text
P3 代码完成
P3 持续运行未完成
```

---

## 4. P4 / P5：双写与读切换

### 4.1 读路径

生产 `.env`：

```text
SCIPAL_READ_CANARY_PERCENT=100
SCIPAL_READ_DETAIL_PERCENT=100
SCIPAL_READ_GRAPH_PERCENT=100
SCIPAL_TENANCY_READ_BACKEND=postgres
```

因此：

```text
/api/papers             100% PG canary
/api/papers/<id>        100% PG canary
/api/papers/<id>/graph  100% PG canary
tenancy 读              PG
```

但：

```text
PG 异常时仍 fallback 到 SQLite
search / evidence / FTS / Chroma 仍以 SQLite/Chroma 为主
```

所以 P5 不是“PG 单轨”，而是“PG 主读 + SQLite 回退”。

### 4.2 写路径

生产 `.env`：

```text
TENANCY_WRITE_BACKEND=postgres
WATCH_WRITE_BACKEND=postgres
PROJECT_WRITE_BACKEND=postgres
EXPERIMENT_WRITE_BACKEND=postgres
CLAIM_WRITE_BACKEND=postgres
REVIEW_WRITE_BACKEND=postgres
SCIPAL_PAPER_WRITE_BACKEND 未设置
```

现状：

```text
tenancy/watch/projects/experiments/claims/reviews  PG-primary
papers 部分路径 PG-first，部分仍 SQLite-first
SQLite outbox trigger 仍有 27 个
outbox pending 0
```

结论：

```text
P4 双写没有关闭
outbox 仍作为 legacy/build 兼容桥
P5 没有全量单轨
```

---

## 5. 老数据校验

### 5.1 ID 级对齐

对 9 张核心表做 SQLite / PG ID 集合比对：

| 表 | SQLite | PG | same | sqlite_only | pg_only |
|---|---:|---:|---:|---:|---:|
| papers | 3,313 | 3,313 | 3,313 | 0 | 0 |
| sections | 69,128 | 69,128 | 69,128 | 0 | 0 |
| paragraphs | 167,388 | 167,388 | 167,388 | 0 | 0 |
| sentences | 862,677 | 862,677 | 862,677 | 0 | 0 |
| citations | 182,817 | 182,817 | 182,817 | 0 | 0 |
| sentence_links | 296,951 | 296,951 | 296,951 | 0 | 0 |
| paper_links | 164,802 | 164,802 | 164,802 | 0 | 0 |
| figures | 13,471 | 13,471 | 13,471 | 0 | 0 |
| tables | 4,922 | 4,922 | 4,922 | 0 | 0 |

结论：

```text
ID 级 100% 对齐
没有发现缺失 ID
```

### 5.2 仍需补的校验

```text
尚未对全部行做文本/字段 checksum
尚未对 JSONB / 数组 / 时间字段做逐行规范化比对
```

所以不能写成：

```text
“老数据 100% 校验无丢失”
```

准确表述：

```text
ID / 行数 100% 对齐
内容级 100% checksum 尚未完成
```

---

## 6. PG 连接池与并发

代码状态：

```text
已新增 services/db/pg_pool.py
ConnectionPool，按 DSN 复用
SCIPAL_PG_POOL_MIN=1
SCIPAL_PG_POOL_MAX=10
SCIPAL_PG_POOL_TIMEOUT=5
读写路径已切换到 pg_connection()
```

当前 PG：

```text
max_connections = 100
实测连接数 = 2（单进程池 min=1, size=2）
```

仍待完成：

```text
生产部署
50/100 并发压测
P95 延迟基线
长跑连接泄漏观察
```

结论：

```text
连接池代码与单元测试完成
生产验收仍未完成
不能仅凭连接池就声称已抗住多用户并发
```

---

## 7. 测试

当前测试：

```text
824 tests OK
```

但：

```text
大多数测试使用 SQLite / tempfile / fake connector
PG 相关测试主要是 unit/mock，不是完整 live PG
没有证据显示 824 项全部跑在真实 PostgreSQL 上
```

结论：

```text
测试全绿：是
全部跑在 PG：否
PG 集成测试：不足
```

---

## 8. P6 归档状态

P6 要求：

```text
连续 30 天无回退
SQLite 标记 archive，不再写
至少两份异地备份
更新 README / 架构图
```

当前：

```text
SQLite 仍可写（mirror/outbox）
27 个 trigger 仍在
没有 30 天观察记录
没有 SQLite archive 标记
没有自动异地备份
```

结论：

```text
P6 未完成
不能删除旧 SQLite
```

---

## 9. Next Steps

| 优先级 | 动作 | 验收 |
|---|---|---|
| P0 | 修复 `deploy/backup.py` 重复 `research.db` | tar 内只有一个 DB |
| P0 | 配置每日/每周自动备份 | 有任务、有日志、有告警 |
| P0 | 每月恢复演练 | 从备份恢复到临时目录并 integrity_check |
| P1 | 引入 `psycopg_pool.ConnectionPool` | min/max/timeout 可配 |
| P1 | 并发压测 | 50/100 并发无池耗尽 |
| P3 | 每日 shadow read | 差异报告自动生成 |
| P4 | 逐表关闭 outbox 或明确冻结 | trigger 数量可解释 |
| P5 | 明确 fallback 策略 | PG 故障时行为可观测 |
| P6 | 30 天无回退后再归档 | SQLite 只读、两份备份 |
| 数据 | 全表 row checksum | 内容级 100% 对齐 |
| 测试 | live PG integration suite | 至少核心读写路径跑真 PG |
| 安全 | 轮换 `.env` 中 API key / PG 密码 | 不进入 git，最小权限 |

---

## 10. 验收结论

```text
P0 备份：有条件通过，缺自动化/恢复演练
P1-P2：通过
P3：代码通过，持续运行未通过
P4：未关闭
P5：100% canary，但不是单轨
P6：未完成
老数据：ID 100% 对齐，内容 checksum 未完成
连接池：未配置
测试：824 全绿，但不是全部跑 PG
```

最终判定：

```text
PostgreSQL 基础迁移成功
生产稳定性验收未完成
暂不删除 SQLite
暂不标记 P6
```
