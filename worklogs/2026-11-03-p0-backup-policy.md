# Worklog: P0 备份保留策略（每日 DB + 每周全量）

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

首次全量备份 3.56 GB，30 天约 107 GB，G 盘只有约 53 GB；改为每日 DB、每周全量。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
deploy/backup.py
deploy/docker-compose.yml
deploy/.env.example
scripts/run_backup_loop.py
tests/test_backup.py
tests/test_backup_policy.py
docs/PostgreSQL迁移-最终验收.md
docs/Research_Logs_Index.md
worklogs/2026-11-03-p0-backup-policy.md
```

## 4. 业务逻辑变化

```text
backup.py 新增 scope:
  db   -> 只归档 data/research.db 快照
  full -> data 全目录 + 快照

run_backup_loop:
  默认首次 full
  距上次 full >= 7 天 -> full
  否则 -> db
  状态写 backup_state.json
  db 保留 30 天
  full 保留 28 天
```

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
tests.test_backup + tests.test_backup_policy
6 tests OK

临时库实测：
  第 1 次 -> scipal-full-*.tar.gz
  第 2 次 -> scipal-db-*.tar.gz
  integrity = ok
  papers = 1
```

## 7. 风险 / 外部 API

```text
无新增外部 API
生产 backup-cron 仍跑旧代码，待部署
DB-only archive 实际大小需部署后确认
```

## 8. 首次 daily DB 失败与修复

失败：

```text
[Errno 2] No such file or directory: /app/data/research.db-shm
```

原因：

```text
data 只读挂载
SQLite WAL 需要 -shm
只读连接无法创建 -shm
```

修复：

```text
backup-cron data 改为可写挂载
备份连接改为 sqlite3.connect(db)
仍只调用 SQLite backup API，不写业务数据
```

测试新增 WAL 模式临时库，备份/恢复通过。

## 9. 未完成项

```text
PR Pending Review
部署新 backup-cron
确认每日 DB archive 大小与磁盘余量
异地备份 / 失败告警
```
