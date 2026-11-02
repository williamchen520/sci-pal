# Phase 2：Watch Runs / Items / Seen 写路径

> 日期：2026-11-02  
> 状态：runs/items/seen PG-first；journals/outbox 未收口。

## 1. 已迁移

```text
create_run
finish_run
add_item
mark_item_read
set_item_feedback
mark_seen
```

开关：

```text
SCIPAL_WATCH_WRITE_BACKEND=postgres
```

## 2. 主键策略

`watch_runs` / `watch_items`：

```text
PG 序列返回 id
-> SQLite 显式插入相同 id
```

避免两库主键分叉。

`watch_seen`：

```text
PG INSERT ... ON CONFLICT DO NOTHING
-> SQLite INSERT OR IGNORE
```

## 3. 顺序

```text
PG 写
-> SQLite mirror
```

PG 失败：

```text
WatchWriteError
不写 SQLite
```

## 4. 仍未迁移

```text
watch_profile_journals
papers 写入（ingest）
watch 结束后的 outbox catch-up
```

因此：

```text
watch 主业务表已 PG-first
outbox 仍不能删除
```

## 5. 代码

```text
services/watch/pg_writes.py
services/watch/repo.py
```

## 6. 测试

```text
watch modules 17 tests OK
```

## 7. 生产

```text
SCIPAL_WATCH_WRITE_BACKEND=postgres 已设置
但当前 app 镜像尚未包含 runs/items/seen 代码
```

需要重建镜像后 canary。

## 8. 下一步

```text
1. watch_profile_journals PG-first
2. 重建镜像 + 合成 canary
3. 再评估 outbox 删除
4. papers 写路径
```
