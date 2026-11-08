# 架构变更授权：P4b2b3 tasks/watch 租户表

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P4b2b2 完成

---

## 1. 问题

tasks 与 watch 仍写 public。

数据：

```text
tasks                 477
watch_profiles          1
watch_runs             11
watch_items            16
watch_seen             16
watch_profile_journals  2
```

特殊风险：

```text
watch-cron 是独立容器/进程
app 和 cron 必须同时切租户
否则会一个写 public、一个写租户
```

---

## 2. 变更

改哪一层：

```text
schema + 写入路径（试点）
```

新增租户表：

```text
lib_ws_default.tasks
lib_ws_default.watch_profiles
lib_ws_default.watch_runs
lib_ws_default.watch_items
lib_ws_default.watch_seen
lib_ws_default.watch_profile_journals
```

复制：

```text
tasks 477
watch_* 按 workspace_id=ws_default
```

开关：

```text
SCIPAL_TENANT_PILOT=tasks,watch
```

代码：

```text
services/unified_task_manager.py
services/watch/pg_read.py
services/watch/pg_writes.py
services/watch/repo.py（如用 PG）
```

部署：

```text
app 和 watch-cron 都要带同一开关
```

---

## 3. 理由

```text
tasks 与 watch 是运行态数据
app/cron 分叉比单纯读隔离更危险
```

先复制、默认关闭，验证：

```text
app 写租户
cron 写租户
public 不再增长
```

---

## 4. 影响

复制：

```text
tasks                 477
watch_profiles          1
watch_runs             11
watch_items             16
watch_seen              16
watch_profile_journals   2
```

代码：

```text
任务状态写入
watch 写入/读取
```

部署：

```text
app
watch-cron
```

兼容：

```text
开关关闭 -> public
```

---

## 5. 迁移

步骤：

```text
1. 建 6 张租户表
2. 复制 ws_default 行
3. 加 search_path helper
4. 开关默认关闭
5. 同时部署 app + watch-cron
6. 打开开关
7. 验证任务/watch 写入
```

回滚：

```sql
DROP TABLE IF EXISTS lib_ws_default.watch_profile_journals;
...
```

关闭开关即回 public。

---

## 6. 验证

```text
tenant.tasks                   477
tenant.watch_profiles            1
tenant.watch_runs               11
tenant.watch_items              16
tenant.watch_seen               16
tenant.watch_profile_journals    2

新建任务 -> tenant +1 / public 不变
watch run -> tenant +1 / public 不变
A 组 smoke 无 5xx
```

---

## 7. 需要批准

```text
1. 新增 6 张租户表
2. 复制 ws_default 行
3. 新增 SCIPAL_TENANT_PILOT=tasks,watch
4. app 和 watch-cron 同步切换
5. public 保留
```

批准后先建表复制，开关保持关闭；部署时 app/cron 必须同一批。
