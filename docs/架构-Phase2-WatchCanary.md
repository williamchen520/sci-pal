# Phase 2 Watch Canary

> 日期：2026-11-02  
> 结果：watch profile/journal/run/item/seen 全部 PG+SQLite 一致。

## 1. 部署

```text
image rebuilt from watch PG-first code
app recreated
SCIPAL_WATCH_WRITE_BACKEND=postgres
```

## 2. Canary 内容

```text
create profile
set journals
create run
add item
mark item read
set feedback
mark seen
finish run
```

## 3. 结果

```text
profile 1
journal 1
run     success
item    read / useful
seen    1
```

PG / SQLite 一致：

```text
PG profile/journal/run/seen = 1 / 1 / success / 1
SQLite profile/journal/run/seen = 1 / 1 / success / 1
item status = read, feedback = useful
```

## 4. 发现并修复

首次 canary 失败：

```text
watch_profiles_pkey duplicate key (id=1)
watch_runs_pkey duplicate key (id=1)
```

原因：

```text
历史 outbox 用显式 id 写入 PG
PG serial sequence 没有推进
PG-first create 再次从 1 开始
```

修复：

```text
_ensure_id_sequence(pg, table)
  setval(seq, max(id)+1, false)
create_profile / create_run / create_item 前调用
```

## 5. 清理

canary 数据已删除：

```text
PG     profiles 1, runs 9, items 14, seen 14
SQLite profiles 1, runs 9, items 14
```

两边计数一致。

## 6. 当前边界

watch 表已全部 PG-first：

```text
watch_profiles
watch_profile_journals
watch_runs
watch_items
watch_seen
```

仍不能删 outbox：

```text
papers ingest
```

## 7. 下一步

```text
1. papers 写路径
2. 停 outbox 触发
3. 观察 drift
```
