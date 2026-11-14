# 架构状态：tenant-ready 单租户架构与 Phase 2 Roadmap

> 日期：2026-11-14  
> 项目状态：**【 tenant-ready 单租户架构】**  
> 决策：`TENANT-DELIVERY-001`  
> 关联：讨论 06、E0/E1/E2、S0

---

## 1. 当前项目状态

```text
tenant-ready 单租户架构
```

含义：

```text
代码从一开始使用 TenantContext
产品只交付一个 tenant + main
保留 tenant -> main 联邦
不做 tenant -> tenant
不做完整多租户控制面
```

---

## 2. 当前生效的架构

### 权限

```text
platform
tenant:<id>
library:<id>
```

```text
platform_owner 只有平台能力
tenant_owner 只有租户能力
platform 不默认读租户正文
```

### 联邦

```text
             main
               |
           tenant
```

只允许：

```text
tenant -> main
scope = own | main | both
```

严禁：

```text
tenant -> tenant
```

### 数据平面

```text
tenant context
  database_dsn_ref
  storage_root
  index_prefix
  source_schemas xml/html/pdf
  code_schema code
```

### 已完成的阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| E0 | capability + resource scope | done |
| E1 | federation_catalog + 星形约束 | done |
| E2 | tenant stack 注册/管理员 DDL | done，非产品面 |
| S0 | TenantContext 单租户 | done |

---

## 3. Phase 2 冻结范围

以下阶段**冻结**，不进入当前开发：

| 阶段 | 内容 | 状态 |
|---|---|---|
| E3 | tenant connector | frozen |
| E4 | gateway scope | frozen |
| E5 | tenant→tenant 拒绝测试 | frozen |
| E6 | support access + audit | frozen |
| E7 | ImportSession 全租户 | frozen |
| E8 | 配额、删除、迁移 | frozen |

冻结不是删除：

```text
计划保留
代码骨架保留
恢复条件明确
```

---

## 4. 为什么冻结

```text
真实租户数少
自助开通需求未成立
完整控制面运维成本高
当前优先级是单租户科研功能
```

多租户真正的成本：

```text
provisioning
migration N 个 DB
backup/restore
quota
observability
support access
delete
```

不是“写几张 tenant_id 表”。

---

## 5. 恢复条件

满足任一条件再启动 Phase 2：

```text
1. 真实租户数 > 3
2. 需要自助开通
3. 需要外部客户隔离交付
4. 合规要求独立 DB/备份
5. 需要 tenant 级配额/计费
6. 需要 tenant 间协作
```

恢复前必须重新评审：

```text
隔离粒度
测试矩阵
运维成本
```

---

## 6. Phase 2 Roadmap

### P2-1 Tenant Connector

```text
tenant -> main
短时 token
不共享 DSN
```

### P2-2 Gateway Scope

```text
scope=own/main/both
拒绝 tenant:<other>
```

### P2-3 Peer Deny

```text
tenantA -> tenantB
```

结构性拒绝，不只 UI 隐藏。

### P2-4 Support Access

```text
break-glass
双人审批
限时
全审计
```

### P2-5 ImportSession

```text
XML / HTML / PDF
GitHub / Zenodo / zip
review
build
index
publish
```

### P2-6 Lifecycle

```text
配额
删除
迁移
备份/恢复
```

---

## 7. 不可破坏的约束

```text
1. 主库是唯一联邦中心
2. 租户之间没有联邦边
3. 平台不默认读租户正文
4. 功能对等，权限不对称
5. 来源分库，不强制对齐
6. 解释不写 canonical
7. 自动入库默认不自动发布
```

---

## 8. 当前开发方向

```text
单租户功能交付
  -> 文献解析
  -> CodeRAG
  -> 证据链
  -> 综述
  -> 单租户 + main 联邦
```

不推进：

```text
E3-E8
多租户控制台
自助 provisioning
跨租户协作
```
