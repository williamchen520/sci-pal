# Phase 1：Experiments 写路径（核心片）

> 日期：2026-11-02  
> 状态：create/update PG-first；access/sign 仍 SQLite。

## 1. 已迁移

```text
create_experiment
update_experiment
```

写入内容：

```text
experiments
experiment_revisions
experiment_audit
```

开关：

```text
SCIPAL_EXPERIMENT_WRITE_BACKEND=postgres
默认关闭
```

## 2. 顺序

开启时：

```text
1. 权限 / project / protocol 检查读 SQLite
2. PG 事务：
   experiments
   experiment_revisions
   experiment_audit
3. SQLite mirror 写同样三张表
4. PG 失败 -> ExperimentWriteError，不写 SQLite
```

## 3. 代码

```text
services/experiments/pg_writes.py
services/experiments/service.py
```

## 4. 未迁移

```text
create_access_request
decide_access_request
sign_experiment
```

这些仍只写 SQLite。

因此：

```text
experiments 核心 CRUD 已 PG-first
授权/签名尚未
```

## 5. 当前生产

```text
SCIPAL_EXPERIMENT_WRITE_BACKEND 未设置
```

生产仍走 SQLite。

## 6. 测试

```text
tests/test_experiments_access.py
tests/test_experiments_routes.py
tests/test_experiment_pg_writes.py
```

覆盖：

```text
create/list
update + revision + audit
access request
sign
flag on/off
```

## 7. 风险

```text
PG 成功但 SQLite mirror 失败时，需要 health 对账
access/sign 仍可能在 SQLite/PG 分叉
```

## 8. 下一步

```text
1. access requests PG-first
2. signatures PG-first
3. 生产 canary
4. 再开 Phase 2（papers/watch）
```
