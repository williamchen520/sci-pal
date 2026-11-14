# E1 计划表：Federation Catalog 与星形约束

> 阶段：E1  
> 状态：已完成  
> 依赖：E0  
> 目标：只登记 tenant→main 联邦；结构性拒绝 tenant→tenant。

---

## 1. 目标

```text
federation_catalog
  只存元数据
  只登记 main 目标
  allowed_scopes 只能是 own/main/both
  不登记 peer tenant
```

---

## 2. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D1-1 | 目录位置 | 控制面 core DB |
| D1-2 | 目标类型 | 只允许 `target_kind=main` |
| D1-3 | peer 字段 | `target_tenant_id` 必须为 NULL |
| D1-4 | scope | `own` / `main` / `both` 子集 |
| D1-5 | 登记权限 | 平台 `platform.federation.manage` |
| D1-6 | 查询权限 | 租户 `tenant.read` 自己租户 |
| D1-7 | 无目录时 | 只能 `own` |

---

## 3. 任务表

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| E1.1 | catalog 迁移 | `deploy/sql/044_federation_catalog.sql` | 表存在，CHECK 生效 |
| E1.2 | 目标约束 | 同上 | `tenant` 目标插入失败 |
| E1.3 | 服务层 | `services/federation/catalog.py` | register/list/resolve |
| E1.4 | 平台登记 | 同上 | 非平台权限拒绝 |
| E1.5 | 租户查询 | 同上 | 只能列自己 |
| E1.6 | 单测 | `tests/test_federation_catalog.py` | 覆盖拒绝 |
| E1.7 | 文档 | 本文件 + JSON | 与实现一致 |

---

## 4. 表结构

```sql
federation_catalog (
  catalog_id,
  tenant_id,
  library_id,
  source_kind,
  target_kind,        -- 只能是 main
  target_tenant_id,   -- 必须 NULL
  allowed_scopes,     -- own/main/both
  db_ref,
  index_name,
  status,
  created_at
)
```

约束：

```text
CHECK target_kind = 'main'
CHECK target_tenant_id IS NULL
CHECK allowed_scopes <@ ARRAY['own','main','both']
UNIQUE (tenant_id, library_id)
```

---

## 5. 服务接口

```text
register_main_link(principal, tenant_id, library_id, ...)
list_links(principal, tenant_id)
resolve_catalog_scope(principal, tenant_id, requested)
assert_star_target(target_kind, target_tenant_id)
```

---

## 6. 不在 E1 范围

```text
不做 tenant provisioning
不做 connector
不做 gateway
不做真实跨库查询
不做平台 support access
```

---

## 7. 验收结果

```text
9 tests passed
DB CHECK: tenant target rejected
```

## 8. 验收

```text
1. 表只允许 target_kind=main
2. target_tenant_id 非空插入失败
3. 非平台权限不能登记
4. 租户只能列自己的 link
5. 无 link 时 main/both 被拒绝
6. tenant:other 请求被拒绝
7. 单测通过
```

---

## 9. 风险

```text
1. 表建在 core 但实际查询在 corpus
2. 租户凭据过宽
3. 后续 gateway 绕过 catalog
4. allowed_scopes 与 E0 解析不一致
```
