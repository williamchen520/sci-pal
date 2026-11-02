# Phase 2：Claims / Reviews 写路径（第一片）

> 日期：2026-11-02  
> 状态：review project create PG-first；claims 仍 SQLite。

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

## 3. 仍未迁移

```text
review_events
claims / claim_cards
claim_card_evidence
claim_card_events
```

因此：

```text
review project 创建已 PG-first
claims 整体仍 SQLite + outbox
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
