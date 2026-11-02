# Phase 2：Claims / Reviews 写路径（第一片）

> 日期：2026-11-02  
> 状态：review project/event + claims create/evidence/update 已 PG-first。

## 1. 已迁移

```text
review/systematic.create_project
```

开关：

```text
SCIPAL_REVIEW_WRITE_BACKEND=postgres
```

顺序：

```text
PG insert review_projects
-> SQLite insert
-> PG 失败 -> ReviewWriteError
```

## 2. 代码

```text
services/review/pg_writes.py
services/review/systematic.py
```

## 3. Claims

已迁移：

```text
create_claim
  claim_cards
  claim_card_events (create)

add_evidence
  claim_card_evidence
  claim_card_events (evidence:*)
```

开关：

```text
SCIPAL_CLAIM_WRITE_BACKEND=postgres
```

已迁移：

```text
claim review_note
claim writing_brief
claim decision
review_events
```

因此：

```text
claims create/evidence/update 已 PG-first
review project/event 已 PG-first
claims/reviews outbox 可进入退役评估
```

## 4. 当前生产

```text
SCIPAL_REVIEW_WRITE_BACKEND 未设置
```

## 5. 测试

```text
tests.test_systematic_review
tests.test_review_repository
  16 tests OK
```

## 6. 下一步

```text
1. review_events PG-first
2. claims create/evidence/events PG-first
3. 再删 claims/reviews outbox
```

## 7. 生产 Canary（2026-11-02）

覆盖：

```text
review project create
review event
claim create
claim evidence
claim note
writing brief
claim decision
```

结果：

```text
project        1 / 1
review_event   1 / 1
claim decision accept / accept
evidence       1 / 1
events         5 / 5
```

清理后：

```text
PG claims 10, review_projects 1, review_events 0
SQLite claims 10, review_projects 1
```

## 8. Canary 发现

首次 `add_evidence` 失败：

```text
PG claim_card_evidence 没有 (claim_id,node_id,relation) 唯一约束
ON CONFLICT 无法匹配
```

修复：

```text
ON CONFLICT (evidence_id)
```

evidence_id 由 claim/node/relation 确定性生成，语义等价。

## 9. 部署说明

本次 canary 镜像由运行容器 `docker commit` 生成，因为正规构建在重复下载
CUDA 依赖。成功 canary 后仍需用 clean git archive 重建一次，避免镜像来源
不可复现。
