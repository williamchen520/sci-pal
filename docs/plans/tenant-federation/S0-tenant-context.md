# S0 计划表：TenantContext 单租户优先

> 阶段：S0  
> 状态：planned  
> 依赖：E0/E1；E2 可选  
> 目标：代码使用 TenantContext，但产品只交付一个 tenant + main。

---

## 1. 目标

```text
一个 tenant
  + main
  + tenant -> main 联邦
  + 不做 tenant -> tenant
```

S0 不实现自助开通、配额、connector、gateway。

---

## 2. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D0-1 | 交付形态 | 单租户 + main |
| D0-2 | 上下文 | 所有新入口用 TenantContext |
| D0-3 | 连接 | context 解析 DSN，不读全局变量 |
| D0-4 | 存储 | context.storage_root |
| D0-5 | 索引 | context.index_prefix |
| D0-6 | 联邦 | 只允许 own/main |
| D0-7 | 恢复多租户 | E3–E8 保持 deferred |

---

## 3. 任务表

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| S0.1 | TenantContext 数据类 | `services/tenancy/context.py` | 字段完整 |
| S0.2 | 单租户解析 | 同上 | 默认 tenant + main |
| S0.3 | 连接/存储/索引解析 | 同上 | 不直接读全局 DSN |
| S0.4 | 静态审计 | `scripts/audit_tenant_context.py` | 新入口不绕过 |
| S0.5 | 单租户 + main smoke | `tests/test_tenant_context.py` | 通过 |
| S0.6 | 文档 | 本文件 + JSON | 与实现一致 |

---

## 4. TenantContext 字段

```text
tenant_id
database_dsn_ref
storage_root
index_prefix
main_federation_enabled
source_schemas
code_schema
```

不存明文密码；只存 DSN 引用/解析结果。

---

## 5. 不在 S0 范围

```text
自助开通
多租户控制台
E3 connector
E4 gateway
E7 ImportSession 全租户
E8 配额/删除/迁移
```

---

## 6. 验收

```text
1. 默认 tenant 可解析
2. main 联邦开关可解析
3. 不直接读取全局 SCIPAL_PG_* 作为业务默认
4. 单租户 smoke 通过
5. 两租户隔离测试只作为回归，不扩大产品面
```

---

## 7. 恢复 E3–E8 条件

```text
租户数 > 3
需要自助开通
需要外部客户隔离
合规要求独立 DB/备份
需要配额/计费
```
