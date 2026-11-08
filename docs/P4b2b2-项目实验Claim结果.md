# P4b2b2 项目/实验/Claim 租户表结果

> 日期：2026-11-08  
> 状态：**租户表复制完成；开关默认关闭**  
> 前置：P4b2b2 授权

---

## 1. 租户表

```text
lib_ws_default.projects                   1
lib_ws_default.project_members            2
lib_ws_default.experiments                0
lib_ws_default.experiment_runs            0
lib_ws_default.experiment_revisions       0
lib_ws_default.experiment_audit           0
lib_ws_default.experiment_signatures      0
lib_ws_default.experiment_access_requests 0
lib_ws_default.claim_cards               10
lib_ws_default.claim_card_evidence       17
lib_ws_default.claim_card_events         55
```

public 保留原行。

---

## 2. 归属字段

补充：

```text
project_members.workspace_id
claim_card_evidence.workspace_id
claim_card_events.workspace_id
```

均回填 `ws_default`。

---

## 3. 读取验证

开关：

```text
SCIPAL_TENANT_PILOT=projects,experiments,claims
```

结果：

```text
projects.list_projects  = 1
claims.pg_read          = 10
experiments.pg_read     = 0
```

无异常。

---

## 4. 权限

```text
scipal_main_reader:
  USAGE + SELECT on lib_ws_default
```

---

## 5. 未做

```text
生产开关未打开
写路径未做真实新增
tasks / watch 未搬
tenant_writer 未接
```

---

## 6. 回滚

```sql
DROP TABLE IF EXISTS lib_ws_default.claim_card_events;
...
```

关闭开关即回 public。
