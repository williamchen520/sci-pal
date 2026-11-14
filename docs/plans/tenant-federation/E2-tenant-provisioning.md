# E2 计划表：Tenant Provisioning

> 阶段：E2  
> 状态：已完成  
> 依赖：E1  
> 目标：为租户生成独立数据库/schema/存储/索引命名空间，并记录状态。

---

## 1. 目标

```text
tenant_id
  -> database_name
  -> source schemas: xml/html/pdf
  -> code schema: code
  -> storage_prefix
  -> index_prefix
```

应用进程只做注册和计划；实际 `CREATE DATABASE` 由管理员 DDL 入口执行。

---

## 2. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D2-1 | 隔离粒度 | v1 一租户一 DB |
| D2-2 | source 隔离 | DB 内 `xml` / `html` / `pdf` schema |
| D2-3 | code 隔离 | 同 DB `code` schema |
| D2-4 | 命名 | `scipal_tenant_<slug>` |
| D2-5 | 存储 | `data/tenants/<slug>/` |
| D2-6 | 索引 | `tenant:<slug>:` |
| D2-7 | 权限 | 应用不持有建库超级权限 |
| D2-8 | 执行 | 管理员 CLI / DDL worker |

---

## 3. 任务表

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| E2.1 | stack 注册表 | `deploy/sql/045_tenant_stacks.sql` | 表存在 |
| E2.2 | 命名规则 | `services/tenancy/provisioning.py` | 确定性命名 |
| E2.3 | 存储前缀 | 同上 | 目录创建 |
| E2.4 | 权限门禁 | 同上 | 非平台拒绝 |
| E2.5 | 管理员 DDL CLI | `scripts/provision_tenant.py` | 不默认执行 |
| E2.6 | 单测 | `tests/test_tenant_provisioning.py` | 覆盖规划/拒绝 |
| E2.7 | 文档 | 本文件 + JSON | 与实现一致 |

---

## 4. 表结构

```sql
tenant_stacks (
  tenant_id,
  slug,
  database_name,
  storage_prefix,
  index_prefix,
  code_schema,
  status,        -- planned / provisioned / failed / disabled
  created_at,
  updated_at
)
```

---

## 5. 状态机

```text
planned
  -> provisioned
  -> disabled

planned
  -> failed
```

`planned` 表示应用已登记，但管理员尚未执行 DDL。

---

## 6. 不在 E2 范围

```text
不做 connector
不做 gateway
不做 ImportSession
不做租户数据迁移
不做配额
```

---

## 7. 验收结果

```text
6 tests passed
demo tenant-e2-demo provisioned
schemas xml/html/pdf/code
```

## 8. 验收

```text
1. tenant_id 校验
2. database_name 确定性
3. storage_prefix 创建
4. 非 platform.tenant.manage 拒绝
5. 重复 provision 幂等
6. 未执行 DDL 时状态为 planned
7. 单测通过
```

---

## 9. 风险

```text
1. 应用进程误持超级权限
2. 数据库名注入
3. 迁移 N 个租户 DB
4. 存储目录与 DB 状态不一致
```
