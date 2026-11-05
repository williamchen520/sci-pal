# G3.10f4 watch PG-only 计划

> 日期：2026-11-05  
> 目标：watch 全链路 PG-only，移除 SQLite 读写路径  
> 原则：先建 store，再改 runner，最后切路由；每阶段可回滚

---

## 0. 现状基线

数据已对齐：

```text
watch_profiles          1 / 1
watch_profile_journals  2 / 2
watch_runs             10 / 10
watch_items            14 / 14
watch_seen             14 / 14
```

当前问题：

```text
routes 读 PG（已回滚）
runner 读写 SQLite
repo 写 SQLite + PG mirror
```

生产当前：

```text
watch 读写 SQLite
SCIPAL_WATCH_BACKEND 未设置
```

---

## 1. 阶段表

| 阶段 | 内容 | 主要文件 | 产出 | 验收 |
|---|---|---|---|---|
| P0 | 冻结读开关、备份 | `.env` / backup | watch 读写一致 | API 200 |
| P1 | PG WatchStore | `services/watch/pg_store.py` | profiles/journals/runs/items/seen CRUD | 单测通过 |
| P2 | Runner 改 Store | `services/watch/runner.py` | runner 不再直接 SQLite | 单测 + dry-run |
| P3 | Ingest 改 PG | `runner.py` / `pg_writes.py` | abstract/fulltext 写 PG | PG 行数增长 |
| P4 | Discovery 改 PG | `services/watch/discovery.py` | journals 去 SQLite | discover 成功 |
| P5 | 路由切写 | `routes/watch.py` | 写 PG | API CRUD |
| P6 | 真机 run + 对账 | — | PG run/digest | 全链路 |
| P7 | 清理 SQLite | `repo.py` | 删除旧路径 | 无 SQLite 写 |

---

## 2. P1：PG WatchStore

新增：

```text
services/watch/pg_store.py
```

接口对齐 `repo`：

```text
connect()                      -> None / 占位
list_profiles(conn, owner)
get_profile(conn, id, owner)
create_profile(conn, data)     -> int
update_profile(conn, id, data)
delete_profile(conn, id)
list_journals(conn, id)
set_journals(conn, id, entries)
journal_metrics(conn, issns)
dedup_key(doi,title)
seen(conn, id, key)
paper_exists(conn, doi)
mark_seen(conn, id, key, paper_id)
create_run(conn, id, start, end, owner)
finish_run(conn, run_id, **stats)
get_run(conn, run_id)
list_runs(conn, id, limit)
add_item(conn, run_id, profile_id, item)
list_items(conn, run_id)
```

要点：

```text
conn 参数保留但忽略
所有 SQL 用 %s
sequence 用 RETURNING
```

验收：

```text
PG store 单测
同一份 fixture 与 repo 输出一致
```

---

## 3. P2：Runner 改 Store

`runner.run_profile`：

```text
store = pg_store if pg_mode else repo
conn = repo.connect(db_path)
profile = store.get_profile(conn, profile_id)
...
store.create_run / list_journals / journal_metrics
store.mark_seen / add_item / finish_run
```

删除 runner 内：

```text
conn.execute("UPDATE watch_profiles ...")
conn.execute("DELETE FROM papers ...")
```

改为：

```text
store.update_profile(...)
store.delete_paper(...)
```

验收：

```text
runner 单测
mock store 调用序列
SQLite 不再被写
```

---

## 4. P3：Ingest 改 PG

`ingest_abstract`：

```text
INSERT INTO papers ... ON CONFLICT DO NOTHING
```

`try_fulltext` / `try_oa_pdf`：

```text
DELETE FROM papers WHERE paper_id=%s
```

注意：

```text
pubmed / europepmc 下载仍可走原 ingest
但论文行写 PG
```

验收：

```text
新 abstract paper 在 PG
SQLite papers 不变
```

---

## 5. P4：Discovery 改 PG

`discovery.discover_journals` 当前写：

```text
DELETE FROM watch_profile_journals
INSERT INTO watch_profile_journals
```

改为：

```text
pg_store.delete_journal / upsert_journal
```

验收：

```text
discover 后 PG journals 更新
SQLite journals 不变
```

---

## 6. P5：路由切写

`routes/watch.py`：

```text
POST/PUT/DELETE profiles
PUT journals
POST discover
POST run
POST read/feedback
```

全部走 `pg_store`，读也走 `pg_store`。

开关：

```text
SCIPAL_WATCH_BACKEND=postgres
```

---

## 7. P6：真机验收

步骤：

```text
1. 新建临时 profile
2. 设置 1 个 journal
3. 运行一次 watch
4. 查看 run/items/digest
5. 标记 read/feedback
6. 删除 profile
```

通过标准：

```text
API 200
SQLite watch 表行数不变
PG run/items 增长
digest 非空
```

---

## 8. P7：清理

删除：

```text
repo.py 写路径
runner SQLite 分支
pg_writes mirror 调用
watch 相关 SQLite schema 初始化
```

保留：

```text
历史数据只读备份
```

---

## 9. 风险

| 风险 | 缓解 |
|---|---|
| sequence 落后 | 每次 insert 前/迁移时 setval |
| runner 事务边界 | store 内单事务 |
| 外部 API 超时 | 保持现有 try/except |
| digest 不一致 | 用同一 `_digest` 函数 |
| 回滚 | 保留 `repo` 分支与开关 |

---

## 10. 工作量

```text
P1   ~200 行
P2   ~150 行
P3   ~80 行
P4   ~60 行
P5   ~120 行
P6   ~30 行
P7   ~-800 行（删除）
```

净增约：

```text
+400 行，最终删除 ~800 行
```

---

## 10b. P1 完成

```text
services/watch/pg_store.py
  profiles / journals / runs / items / seen
```

冒烟：

```text
create -> get -> update
set_journals 1
delete -> None
```

测试：

```text
tests.test_watch_pg_store 2 OK
```

生产未启用。

## 10c. P2 完成

```text
runner.run_profile -> store
  repo 默认
  pg_store when SCIPAL_WATCH_PG_STORE=1
```

测试：

```text
tests.test_watch_runner_store 2 OK
tests.test_watch 8 OK
```

修复：

```text
update_profile 允许 last_run_at / next_run_at
last_push_at / last_heartbeat_at
```

注意：

```text
P2 仍保留 raw conn.execute 更新 profile
P3 前不能启用
```

## 10d. P3 完成

```text
ingest_abstract -> PG papers
try_fulltext / try_oa_pdf -> PG 模式暂跳过
runner profile 更新 -> store.update_profile
```

PG store 干跑：

```text
run 12
items 1
abstract 1
```

测试：

```text
tests.test_watch_runner_store 2 OK
tests.test_watch 8 OK
```

修复：

```text
update_profile 允许 last_run_at / next_run_at
last_push_at / last_heartbeat_at
```

## 10e. P4 完成

```text
discovery.discover_journals -> store
  journals 读/写/删
```

冒烟：

```text
journals 1 manual
cleanup ✅
```

测试：

```text
tests.test_watch_discovery_store 2 OK
```

## 11. 执行顺序

```text
P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7
```

每个阶段单独 PR，标准模板正文，测试全绿后再进入下一阶段。
