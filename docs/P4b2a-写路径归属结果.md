# P4b2a 写路径归属结果

> 日期：2026-11-08  
> 状态：**完成；只加归属，不搬表**  
> 前置：P4b2a 授权

---

## 1. 已加字段

```text
reviews
tasks
watch_profiles
watch_runs
watch_items
watch_seen
watch_profile_journals
```

默认：

```text
ws_default
```

索引：

```text
idx_reviews_workspace
idx_tasks_workspace
idx_watch_*_workspace
```

---

## 2. 回填

```text
reviews             29
tasks              477
watch_profiles       1
watch_runs          11
watch_items         16
watch_seen          16
watch_profile_journals 2
```

验证：

```text
所有 workspace_id 非 NULL
reviews_null        0
tasks_null          0
watch_*_null        0
```

---

## 3. 写入默认值

临时插入 review，不显式传 workspace_id：

```text
INSERT INTO reviews (...)
-> workspace_id = ws_default
```

任务/监测写入同样由列默认值兜底。

---

## 4. 回归

```text
/api/health          200
A 组 smoke 31 条      0 个 5xx
```

---

## 5. 未做

```text
不搬表
不建业务表副本
不切 tenant_writer
不改 API
```

P4b2b 才按 workspace 分表/视图。

---

## 6. 回滚

```sql
ALTER TABLE reviews DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE tasks DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE watch_profiles DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE watch_runs DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE watch_items DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE watch_seen DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE watch_profile_journals DROP COLUMN IF EXISTS workspace_id;
```
