# Phase 1 Canary：Projects + Experiments

> 日期：2026-11-02  
> 结果：create/update 通过；access/sign 未在 canary 中覆盖。

## 1. 部署

```text
image built from 2283d21
app recreated
flags:
  SCIPAL_PROJECT_WRITE_BACKEND=postgres
  SCIPAL_EXPERIMENT_WRITE_BACKEND=postgres
```

## 2. Canary 内容

使用临时 protocol + 临时 project：

```text
create project
create experiment
update experiment -> running / revision 2
```

## 3. 结果

```text
PG:
  project       1
  experiment    1
  revisions     2
  audit         2

SQLite:
  project       1
  experiment    1
  revisions     2
  audit         2
```

状态：

```text
experiment status = running
revision = 2
```

## 4. 清理

canary 数据已从 PG 和 SQLite 删除：

```text
PG projects      1 -> 1（原有项目保留）
PG experiments   0
SQLite projects  1
SQLite experiments 0
```

## 5. Access / Sign Canary

使用临时用户与 workspace：

```text
create owner + PI user
create workspace
add PI membership
create project + experiment
PI request access
owner approve
owner sign (password re-auth)
```

结果：

```text
request_status  approved
signature       1
sign audit      1
```

PG / SQLite 一致：

```text
PG request approved, signature 1, sign audit 1
SQLite request approved, signature 1
```

清理后：

```text
PG users 2, workspaces 1, experiments 0, signatures 0
SQLite users 2, workspaces 1, experiments 0
```

## 5.1 仍未覆盖

```text
project add_member
copy_project
```

这些代码已 PG-first，但未在 canary 中执行。

## 6. 当前生产

```text
project flag    on
experiment flag on
app             healthy
/api/health     200
```

## 7. 风险

```text
access/sign 未经真实 PG 执行
如果失败，会走 ExperimentWriteError，不会静默回退
```

## 8. 下一步

```text
1. 补 access/sign canary
2. 观察 SQLite/PG 对账
3. 再开 Phase 2（papers/watch）
```
