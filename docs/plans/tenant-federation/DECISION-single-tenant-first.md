# 决策记录：Tenant-ready 单租户优先

> 日期：2026-11-14  
> 状态：已采纳  
> 关联：讨论 06、E0/E1/E2、执行计划总表

---

## 1. 背景

有人建议不做多租户，因为“写起来简单，测试非常麻烦”。

评估结论：

```text
共享 schema 多租户：写起来简单，泄漏测试难
物理隔离多租户：写起来复杂，隔离测试反而容易
真正的成本在 provisioning / migration / 运维，不只是测试
```

---

## 2. 决策

```text
不做完整 SaaS 多租户控制面
改为 tenant-ready 单租户优先
```

保留：

```text
E0 capability + resource scope
E1 federation_catalog + 星形约束
E2 tenant stack 注册/管理员 DDL（可选）
```

暂停：

```text
E3 tenant connector
E4 gateway scope
E5 peer deny tests
E6 support access
E7 ImportSession 全租户
E8 配额/删除/迁移
```

---

## 3. 当前交付形态

```text
一个 tenant
  + main
  + tenant -> main 联邦
  + 不做 tenant -> tenant
```

代码从一开始使用 `TenantContext`，但不做：

```text
自助开通
多租户控制台
租户配额
跨租户协作
自动 provisioning
```

---

## 4. 恢复条件

满足任一条件再启动 E3–E8：

```text
1. 真实租户数 > 3
2. 需要自助开通
3. 需要外部客户隔离交付
4. 合规要求独立 DB/备份
5. 需要 tenant 级配额/计费
```

---

## 5. 风险

```text
1. 代码里写死全局 DSN
2. tenant_id 渗透到业务逻辑
3. 以后恢复多租户时返工
4. E2 已建的 demo tenant 被误当生产能力
```

缓解：

```text
S0 引入 TenantContext
所有新入口必须从 context 取连接/存储/索引
E3–E8 计划保留，但标记 deferred
```

---

## 6. 结论

```text
架构上多租户就绪
产品上先单租户交付
```

不是放弃多租户，而是延后产品化。
