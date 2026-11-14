# E0 计划表：Capability 与 Resource Scope 模型

> 阶段：E0  
> 状态：已完成  
> 依赖：无  
> 目标：先建立“功能对等、权限不对称”的可执行权限模型，不接数据库、不改路由。

---

## 1. 目标

```text
principal + membership + role + capability + resource scope
```

替代：

```text
is_admin / admin / user
```

E0 只做模型和单测，不做租户开通、不做联邦目录、不改现有 API。

---

## 2. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D0-1 | 权限判断方式 | capability，不判断角色名 |
| D0-2 | 资源范围 | `platform` / `tenant:<id>` / `library:<id>` |
| D0-3 | 平台拥有者 | 只有平台能力，不默认读租户正文 |
| D0-4 | 租户管理员 | 租户内全能力，不能跨租户 |
| D0-5 | 联邦 | 只允许 own/main/both，禁止 tenant-to-tenant |
| D0-6 | 兼容 | 保留现有 `authorize()`，新模型独立接入 |

---

## 3. 任务表

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| E0.1 | capability 常量 | `services/tenancy/capabilities.py` | 能力集合可导入 |
| E0.2 | principal / membership | 同上 | 可表达平台角色、租户角色、library 归属 |
| E0.3 | scope 解析 | 同上 | `tenant:acme` / `library:lib_1` 可解析 |
| E0.4 | can() 判断 | 同上 | 平台/租户/library 三类 scope |
| E0.5 | 星形约束 | 同上 | 拒绝 `tenant:other` |
| E0.6 | 单测 | `tests/test_tenancy_capabilities.py` | 覆盖允许/拒绝 |
| E0.7 | 文档 | 本文件 + JSON | 与实现一致 |

---

## 4. 能力清单

```text
platform.tenant.manage
platform.plugin.manage
platform.federation.manage

tenant.read
tenant.import
tenant.review
tenant.publish
tenant.members.manage
tenant.plugin.enable

library.read
library.write
library.index
```

---

## 5. 角色映射

| 角色 | 能力 |
|---|---|
| platform_owner | `platform.*` |
| tenant_owner | `tenant.*` + `library.*` |
| tenant_admin | `tenant.*` + `library.*` |
| tenant_reviewer | `tenant.read` `tenant.review` `library.read` |
| tenant_member | `tenant.read` `tenant.import` `library.read` `library.write` |
| tenant_viewer | `tenant.read` `library.read` |

---

## 6. 不在 E0 范围

```text
不改数据库
不改 routes
不改 MCP
不实现 federation_catalog
不实现 tenant provisioning
不实现 ImportSession
```

---

## 7. 验收结果

```text
11 tests passed
```

## 8. 验收标准

```text
1. platform_owner 不能 tenant.read
2. tenant_owner 可以 tenant.import 自己租户
3. tenant_owner 不能 tenant.import 其他租户
4. tenant_owner 不能 platform.plugin.manage
5. library scope 必须映射到所属 tenant
6. tenant_viewer 不能 tenant.import
7. allowed_federation_scopes 只返回 own/main/both 的子集
8. 单测通过
```

---

## 9. 风险

```text
1. 新模型与旧 authorize() 并存，入口可能绕过
2. library 到 tenant 的映射缺失
3. 平台支持访问被误当成平台默认权限
4. 后续 API 接入时遗漏 capability 检查
```

缓解：

```text
E1 接入前先加统一 guard
旧 authorize() 标记 legacy
所有新入口必须走 can()
```
