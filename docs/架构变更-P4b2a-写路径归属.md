# 架构变更授权：P4b2a 写路径归属

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P4b1 读连接已切换

---

## 1. 问题

不是所有工作区数据都有 `workspace_id`。

已有：

```text
projects
experiments / runs / revisions / audit / signatures / access_requests
claim_cards
notes
papers
tenancy
```

没有：

```text
reviews
tasks
watch_*（部分）
```

证据：

```text
projects              1
experiments           0
experiment_runs       0
claim_cards          10
notes                 0
reviews              29
tasks               477
```

后果：

```text
reviews/tasks 无法按 workspace 隔离
P4b2 无法直接搬表
租户写入没有归属字段
```

---

## 2. 变更

改哪一层：

```text
schema + 写路径
```

P4b2a 只做归属：

```text
reviews 增加 workspace_id
tasks 增加 workspace_id
watch_profiles / watch_runs / watch_items 检查并补 workspace_id
```

默认值：

```text
ws_default
```

回填：

```text
reviews 29 -> ws_default
tasks 477 -> ws_default
```

不搬表：

```text
不创建 lib_ws_default 业务表
不改应用写表名
不切 tenant_writer
```

---

## 3. 理由

```text
先有归属，才能谈隔离
没有 workspace_id 就搬表，只会把无主数据搬进租户
```

P4b2a 是 P4b2b 的前置：

```text
P4b2a 加字段 + 回填
P4b2b 再按 workspace 分表/视图
P4b2c 再切 tenant_writer
```

---

## 4. 影响

表：

```text
reviews             29 行
tasks              477 行
watch_*            需要先盘点
```

代码：

```text
写入 reviews 时带 workspace_id
写入 tasks 时带 workspace_id
watch 写入带 workspace_id
```

现有 API：

```text
响应不变
默认 workspace 行为不变
```

---

## 5. 迁移

步骤：

```text
1. 检查 watch 表是否已有 workspace_id
2. ALTER TABLE ADD COLUMN workspace_id
3. 回填 ws_default
4. 加索引
5. 写入路径补字段
6. 验证
```

回滚：

```sql
ALTER TABLE reviews DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE tasks DROP COLUMN IF EXISTS workspace_id;
```

---

## 6. 验证

```text
reviews.workspace_id 无 NULL
tasks.workspace_id 无 NULL
watch 表无 NULL
/reviews /tasks /watch 仍 200
A 组 smoke 无 5xx
```

---

## 7. 需要批准

```text
1. reviews 增加 workspace_id
2. tasks 增加 workspace_id
3. watch_* 按盘点结果补字段
4. 回填 ws_default
5. P4b2a 不搬表、不切 tenant_writer
```

批准后先盘点 watch_*，再执行 ALTER/回填。
