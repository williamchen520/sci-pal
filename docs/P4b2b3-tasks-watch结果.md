# P4b2b3 tasks / watch 租户表结果

> 日期：2026-11-08  
> 状态：**租户表复制完成；开关默认关闭**  
> 前置：P4b2b3 授权

---

## 1. 租户表

```text
lib_ws_default.tasks                   477
lib_ws_default.watch_profiles            1
lib_ws_default.watch_runs               11
lib_ws_default.watch_items              16
lib_ws_default.watch_seen               16
lib_ws_default.watch_profile_journals    2
```

public 保留原行。

---

## 2. tasks 写路径修复

P4b2b3 之前 `create_task / update_progress / complete / fail / cancel` 仍写 SQLite。

本次改为：

```text
SCIPAL_TASKS_BACKEND=postgres
-> PG 写 tasks
-> 租户开关打开时写 lib_ws_default.tasks
```

验证：

```text
create_task      tenant +1
update_progress  成功
complete_task    status=completed
get_task         completed
public.tasks     0
```

清理后恢复基线。

---

## 3. watch 读取

```text
SCIPAL_TENANT_PILOT=tasks,watch
watch.pg_read.list_profiles() = 1
```

---

## 4. 开关

```text
SCIPAL_TENANT_PILOT=tasks,watch
```

默认关闭。

注意：

```text
app 和 watch-cron 必须同一批切换
```

---

## 5. 未做

```text
生产开关未打开
watch-cron 未同步切换
tenant_writer 未接
```

---

## 6. 回滚

```sql
DROP TABLE IF EXISTS lib_ws_default.watch_profile_journals;
...
```

关闭开关即回 public。
