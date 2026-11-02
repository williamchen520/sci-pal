# Phase 2：Watch Profile 写路径（第一片）

> 日期：2026-11-02  
> 状态：profile create/update/delete PG-first；runs/items/seen 仍 SQLite。

## 1. 已迁移

```text
create_profile
update_profile
delete_profile
```

开关：

```text
SCIPAL_WATCH_WRITE_BACKEND=postgres
```

## 2. 顺序

开启时：

```text
1. PG 先写 watch_profiles
2. SQLite 用同一个 id 写 mirror
3. PG 失败 -> WatchWriteError，不写 SQLite
```

`create_profile` 使用 PG 序列返回的 id，SQLite 显式插入相同 id，避免两库主键分叉。

## 3. 代码

```text
services/watch/pg_writes.py
services/watch/repo.py
```

## 4. 未迁移

```text
watch_runs
watch_items
watch_seen
watch_profile_journals
```

这些仍 SQLite 主写 + outbox。

因此：

```text
profile 生命周期 PG-first
watch run 数据仍 SQLite
outbox 还不能删除
```

## 5. 当前生产

```text
SCIPAL_WATCH_WRITE_BACKEND=postgres 已设置
但当前 app 镜像尚未包含本片代码
```

需要重建镜像后才会生效。

## 6. 测试

```text
watch modules 17 tests OK
```

## 7. 下一步

```text
1. watch runs/items/seen PG-first
2. 再考虑移除 watch outbox
3. papers 写路径
```
