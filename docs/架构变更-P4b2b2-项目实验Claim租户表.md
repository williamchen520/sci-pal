# 架构变更授权：P4b2b2 项目/实验/Claim 租户表

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P4b2b1 试点通过

---

## 1. 问题

P4b2b1 只覆盖 reviews/notes；项目、实验、claim 仍在 public。

证据：

```text
projects                  1
project_members           2
experiments               0
experiment_*              0
claim_cards              10
claim_card_evidence      17
claim_card_events        55
```

依赖：

```text
pg_constraint 查询
-> projects/experiments/claim_cards 无外键
```

后果：

```text
这三组业务仍写 public
租户隔离只覆盖 reviews/notes
```

---

## 2. 变更

改哪一层：

```text
schema + 写入路径（试点）
```

新增租户表：

```text
lib_ws_default.projects
lib_ws_default.project_members
lib_ws_default.experiments
lib_ws_default.experiment_runs
lib_ws_default.experiment_revisions
lib_ws_default.experiment_audit
lib_ws_default.experiment_signatures
lib_ws_default.experiment_access_requests
lib_ws_default.claim_cards
lib_ws_default.claim_card_evidence
lib_ws_default.claim_card_events
```

按 `LIKE public.<table> INCLUDING ALL` 建表。

补充归属字段：

```text
project_members.workspace_id
claim_card_evidence.workspace_id
claim_card_events.workspace_id
```

回填 `ws_default`，通过父表关联。

开关：

```text
SCIPAL_TENANT_PILOT=projects,experiments,claims
```

默认关闭。

代码：

```text
projects/pg_service.py
experiments/pg_read.py / pg_write.py
claims/service.py / pg_read.py / pg_writes.py
```

---

## 3. 理由

```text
三组表无外键，复制风险低
行数小
可以先复制、开关默认关、再逐组打开
```

不做：

```text
不删除 public
不切 tenant_writer
不搬 tasks/watch
```

---

## 4. 影响

复制：

```text
projects                  1
project_members           2
claim_cards              10
claim_card_evidence      17
claim_card_events        55
experiments               0
```

代码：

```text
三个 service 组增加 search_path 切换
```

兼容：

```text
开关关闭 -> public
开关打开 -> 租户表
```

---

## 5. 迁移

步骤：

```text
1. 建 11 张租户表
2. 补 3 个归属字段
3. 复制 ws_default 行
4. 加 search_path helper 支持
5. 开关默认关闭
6. 单端点验证
```

回滚：

```sql
DROP TABLE IF EXISTS lib_ws_default.claim_card_events;
...
```

关闭开关即回 public。

---

## 6. 验证

```text
tenant.projects            1
tenant.project_members     2
tenant.claim_cards        10
tenant.claim_card_evidence 17
tenant.claim_card_events  55

开关打开：
  GET /api/projects       200
  GET /api/claims         200
  GET /api/experiments    200

public 计数不变
A 组 smoke 无 5xx
```

---

## 7. 需要批准

```text
1. 新增 11 张租户表
2. 补 3 个归属字段
3. 复制 ws_default 行
4. 新增 SCIPAL_TENANT_PILOT 三组开关
5. public 保留
```

批准后先建表复制，开关保持关闭。
