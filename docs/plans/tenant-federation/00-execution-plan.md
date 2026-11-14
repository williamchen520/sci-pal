# 租户联邦执行计划总表

> 日期：2026-11-14  
> 版本：v1  
> 状态：执行中  
> 当前阶段：E2  
> 机器可读：`00-execution-plan.json`

---

## 1. 目标

```text
租户与主库同构
功能对等
权限不对称
物理隔离
星形联邦
```

最终形态：

```text
             main
           /  |  \
      tenantA tenantB tenantC
```

允许：

```text
tenant -> main
```

严禁：

```text
tenant -> tenant
```

---

## 2. 执行原则

```text
1. 先权限模型，再数据平面，再联邦
2. 每阶段先写 .md + .json 计划表
3. 每阶段一个 PR
4. 每阶段有验收测试
5. 未合并前不进入下一阶段
6. 不允许跳过 E0/E1 直接做 ImportSession
```

---

## 3. 总表

| 阶段 | 目标 | 依赖 | 状态 | 计划表 | 主要验收 |
|---|---|---|---|---|---|
| E0 | capability + resource scope | — | done | `E0-capability-scope.md/.json` | 11 tests |
| E1 | federation_catalog + 星形约束 | E0 | done | `E1-federation-catalog.md/.json` | catalog 只登记 main；拒绝 peer |
| E2 | tenant provisioning | E1 | planned | `E2-tenant-provisioning.md/.json` | DB/storage/index namespace |
| E3 | tenant connector | E2 | planned | `E3-tenant-connector.md/.json` | 只允许 main；短时 token |
| E4 | gateway scope | E3 | planned | `E4-gateway-scope.md/.json` | own/main/both |
| E5 | tenant→tenant 拒绝测试 | E4 | planned | `E5-peer-deny-tests.md/.json` | 结构性拒绝 |
| E6 | support access + audit | E5 | planned | `E6-support-access-audit.md/.json` | break-glass + 双人审批 |
| E7 | ImportSession 接租户 | E6 | planned | `E7-import-session.md/.json` | XML/PDF/HTML/code 分流 |
| E8 | 配额、删除、迁移 | E7 | planned | `E8-quota-delete-migration.md/.json` | 生命周期闭环 |

---

## 4. 阶段说明

### E0 capability + resource scope

```text
principal
membership
role
capability
resource scope
```

产物：

```text
services/tenancy/capabilities.py
tests/test_tenancy_capabilities.py
```

状态：

```text
done
11 tests passed
PR #816
```

### E1 federation_catalog

```text
只登记 main 联邦
不登记 tenant->tenant
scope 只允许 own/main/both
```

产物：

```text
deploy/sql/*_federation_catalog.sql
services/federation/catalog.py
tests/test_federation_catalog.py
```

### E2 tenant provisioning

```text
tenant
  DB
  schema
  storage prefix
  index namespace
  code DB
```

### E3 tenant connector

```text
tenant -> main
短时 token
不共享 DSN
不共享数据库账号
```

### E4 gateway scope

```text
scope=own
scope=main
scope=both
```

拒绝：

```text
tenant:<other>
```

### E5 peer deny tests

```text
tenantA -> tenantB
tenantB -> tenantC
```

必须结构性失败，不只 UI 隐藏。

### E6 support access + audit

```text
break-glass
双人审批
限时
全审计
```

### E7 ImportSession 接租户

```text
XML / HTML / PDF
GitHub / Zenodo / zip
review
build
index
publish
```

### E8 配额、删除、迁移

```text
quota
retention
delete
migration
backup/restore
```

---

## 5. 决策记录

| 编号 | 决策 | 结论 |
|---|---|---|
| D1 | 隔离粒度 | v1 一租户一 DB + source schema |
| D2 | 联邦目录 | 控制面 core DB，只存元数据 |
| D3 | 主库联邦 | v1 只读查询，不做订阅复制 |
| D4 | 租户凭据 | 短时 token + connector，不共享 DSN |
| D5 | 支持访问 | break-glass + 双人审批 + 限时 |
| D6 | 跨租户协作 | 只允许主库中转/显式导出 |
| D7 | 租户删除 | 撤销联邦、停 connector、清索引、留审计 |
| D8 | 插件治理 | 平台批准版本，租户启用子集 |

---

## 6. 计划文件规范

每个阶段必须有：

```text
E<n>-<name>.md
E<n>-<name>.json
```

JSON 至少包含：

```json
{
  "plan_id": "E<n>",
  "title": "...",
  "status": "planned | in_progress | done | blocked",
  "depends_on": [],
  "tasks": [],
  "acceptance": [],
  "files": []
}
```

---

## 7. 执行门禁

```text
E0  done
E1  done
E2  需要先写计划表
E3  依赖 E2 合并
E4  依赖 E3 合并
E5  依赖 E4 合并
E6  依赖 E5 合并
E7  依赖 E6 合并
E8  依赖 E7 合并
```

---

## 8. 当前下一步

```text
E1 federation_catalog
  -> 先写 E1 .md/.json
  -> 建 catalog 表
  -> 只允许 main
  -> 拒绝 tenant->tenant
  -> 测试
```
