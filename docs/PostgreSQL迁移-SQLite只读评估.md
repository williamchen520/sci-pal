# SQLite 只读评估

日期：2026-11-06

## 1. 目标

判断生产 SQLite 是否可切 `PRAGMA query_only=ON`。

## 2. 观测

重启 app 后：

```text
research.db size        1,837,252,608
research.db mtime       2026-11-06 04:47:37
wal size                0
```

调用读接口：

```text
/api/health
/api/watch/profiles
/api/projects
/api/review-projects
```

再次检查：

```text
research.db size        不变
research.db mtime       不变
wal                     无写入帧
```

## 3. 静态检查

以下模块已 PG 化，但仍有 SQLite fallback/回滚路径：

```text
services/review/notifications.py
services/review/review_repository.py
services/claims/service.py
services/protocols/service.py
services/watch/repo.py
services/watch/runner.py
services/tenancy/service.py
services/search/ingest.py
services/search/online_downloader.py
services/trust/retraction.py
```

生产开关：

```text
SCIPAL_SYSTEMATIC_BACKEND=postgres
SCIPAL_CLAIMS_BACKEND=postgres
SCIPAL_PROTOCOLS_BACKEND=postgres
SCIPAL_WATCH_PG_STORE=1
SCIPAL_TENANCY_PG_ONLY=1
SCIPAL_INGEST_PG_ONLY=1
```

## 4. 结论

```text
当前没有观察到运行时 SQLite 写入
但不能直接 chmod 只读
```

原因：

```text
1. 仍有 fallback 分支
2. 仍有 SQLite 直接连接
3. watch repo 未删除
4. WAL/SHM 需要可写
```

## 5. 建议

先做：

```text
P7a 删除 watch repo SQLite 路径
P7b 清理 SQLite fallback
P7c 统一 sqlite 连接工厂
P7d 再加 query_only 开关
```

不要：

```text
直接 chmod 444
直接 PRAGMA query_only 全局
```

## 6. 当前状态

```text
SQLite 仍可写
生产健康
检索无回退
```


---

## 7. 已启用 query_only

生产：

```text
SCIPAL_SQLITE_QUERY_ONLY=1
```

实现：

```text
services/db/sqlite_readonly.py
  仅对 research.db 加 PRAGMA query_only
  Chroma/其它 db 不受影响
```

启动时：

```text
跳过 migrate_watch / migrate_claim_pilot
```

验证：

```text
health 200
watch profiles 200
review-projects 200
create/delete watch profile 成功（PG）
research.db mtime 不变
```

结论：

```text
research.db 运行时只读
写入全部走 PG
```

## 8. 注意

```text
SQLite 文件本身仍可写
query_only 是连接级
脚本/构建进程不受影响
```


---

## 9. watch cron 残留

发现：

```text
scripts/run_watch_due.py
  build_db.watch_schema.migrate(db)
services/watch/scheduler.py
  repo.connect(db)
```

已修：

```text
scheduler.due_profiles -> PG when pg_store
run_watch_due 不再 SQLite migrate
```

冒烟：

```text
due_profiles -> 0
```


---

## 10. 发现：WAL/SHM 缺失

现象：

```text
app 运行时新开 sqlite3.connect(research.db)
-> unable to open database file
immutable=1 可读
app 停止后可正常打开
```

根因：

```text
research.db journal_mode=wal
但 -wal / -shm 缺失
新连接无法建立
```

修复：

```text
停止 app
PRAGMA journal_mode=DELETE
启动 app
```

验证：

```text
app 运行时新连接可读
papers 3313
health 200
watch profiles 1
```

## 11. cron entrypoint

发现：

```text
watch-cron / health-cron / backup-cron
entrypoint 忽略 command
实际都在跑 Flask
```

修复：

```text
docker-compose.yml
  entrypoint: []
```

验证：

```text
watch-cron  -> watch scheduler started
health-cron -> health report
```


---

## 12. health 预期差异

`papers`：

```text
sqlite 3313
postgres 3315
expected_pg_only 2
```

2 篇为：

```text
paper_watch_*
```

健康检查现在允许“仅 PG 的 watch 论文”，不再 degraded。


---

## 13. 启动期 migrate 移除

`api_server.py` 不再：

```text
import migrate_watch
import migrate_claim_pilot
call 两者
```

PG-only 应用启动不再触碰 SQLite schema。


---

## 14. JATS PG 导入

新增：

```text
build_db/import_jats_pg.py
```

覆盖：

```text
paper / sections / paragraphs / sentences
figures / tables / citations / sentence_links
```

接入：

```text
SCIPAL_INGEST_PG_ONLY=1
import_jats.import_file -> import_jats_pg
import_dir -> PG-only
```

冒烟：

```text
19 paragraphs
87 sentences
39 links
cleanup ✅
```
