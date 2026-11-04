# G3.5 claims 盘点

> 日期：2026-11-05  
> 结论：claims 需要 service 层 PG 适配，不能只改 env

---

## 1. 当前结构

```text
routes/claims.py
  service.connect(db_path) -> sqlite3
  service.list_claims/get_claim/create/...
```

写路径：

```text
services/claims/pg_writes.py
  create_claim
  add_evidence
  update_claim
```

现状：

```text
SQLite 是主
PG 是 mirror
```

---

## 2. 需要迁移的函数

| 函数 | 类型 | PG 状态 |
|---|---|---|
| list_claims | 读 | ❌ 仅 SQLite |
| get_claim | 读 | ❌ 仅 SQLite |
| create_claim | 写 | 🟡 PG mirror |
| add_evidence | 写 | 🟡 PG mirror |
| decide | 写 | 🟡 PG mirror |
| add_note | 写 | ❌ SQLite |
| search_candidates | 读 | ❌ SQLite |
| interrogate | 读 | ❌ SQLite |
| set_writing_brief | 写 | 🟡 PG mirror |

---

## 3. PG 表

```text
claim_cards
claim_card_events
claim_card_evidence
```

---

## 4. 拆分子任务

```text
G3.5a PG read adapter
  list_claims
  get_claim

G3.5b PG write adapter
  create_claim
  add_evidence
  decide
  add_note
  set_writing_brief

G3.5c search/interrogate
  search_candidates 读 PG
  interrogate 保持调用 retriever

G3.5d 路由切换
  SCIPAL_CLAIMS_BACKEND=postgres

G3.5e 冒烟
  create/list/evidence/decision/note
```

---

## 5. 验收

```text
1. 新 claim 只写 PG
2. SQLite claim 表行数不增长
3. 事件顺序正确
4. 现有 claims 可读
5. claims 路由测试全绿
```

---

## 6. 当前生产

```text
claims 仍 SQLite primary
PG mirror 继续
app healthy
```

---

## 6b. G3.5a 完成

```text
services/claims/pg_read.py
routes/claims.py
  SCIPAL_CLAIMS_BACKEND=postgres
```

冒烟：

```text
list 5 条
detail evidence 3 / events 10
```

测试：

```text
tests.test_claims_pg_read 2 OK
全量 885 tests OK
```

写路径仍 SQLite。

## 7. 下一步

```text
G3.5a PG read adapter
```

先只切读，验证 PG 数据完整，再切写。
