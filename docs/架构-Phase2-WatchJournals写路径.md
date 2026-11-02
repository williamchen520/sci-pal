# Phase 2：Watch Profile Journals 写路径

> 日期：2026-11-02  
> 状态：journals PG-first；watch 写路径基本收口。

## 1. 已迁移

```text
set_journals        delete + insert
delete_journal      auto ISSN removal
```

开关：

```text
SCIPAL_WATCH_WRITE_BACKEND=postgres
```

顺序：

```text
PG 先 replace/delete
-> SQLite mirror
-> PG 失败 -> WatchWriteError
```

## 2. 代码

```text
services/watch/pg_writes.py
services/watch/repo.py
services/watch/discovery.py
```

## 3. watch 写路径现状

已 PG-first：

```text
watch_profiles
watch_profile_journals
watch_runs
watch_items
watch_seen
```

仍 SQLite：

```text
papers ingest
watch run 结束后的 outbox catch-up
```

## 4. 还不能删 outbox 的原因

```text
papers 插入仍经 SQLite + outbox
历史数据/其他表仍有 outbox 触发
```

## 5. 测试

```text
watch modules 17 tests OK
```

## 6. 下一步

```text
1. 重建镜像 + watch canary
2. papers 写路径
3. 清 outbox
```
