# G3.1 写入路径盘点

> 日期：2026-11-05  
> 目标：找出所有 SQLite 运行时写入，拆分到可迁移任务  
> 约束：G3 完成前不删除 SQLite/Chroma

---

## 1. SQLite 当前状态

```text
dualwrite trigger   27
FTS trigger         12
outbox 总数         249
outbox pending      0
```

Dual-write 表：

```text
papers
sections
paragraphs
sentences
figures
tables
citations
sentence_links
paper_links
```

FTS 表：

```text
papers_fts
paragraphs_fts
sentences_fts
summaries_fts
```

---

## 2. 写入路径分类

| 路径 | 当前写入 | 目标 | 优先级 |
|---|---|---|---|
| 论文解析入库 | SQLite + PG 同步 | PG-only | P0 |
| 论文元数据更新 | PG-first + SQLite mirror | PG-only | P1 |
| notes | SQLite | PG | P1 |
| claims | PG + SQLite 混合 | PG-only | P1 |
| experiments | PG + SQLite 混合 | PG-only | P1 |
| data audit | SQLite | PG | P2 |
| outbox replay | SQLite -> PG | 删除 | P0 |
| FTS trigger | SQLite FTS | ParadeDB | 已完成读，待删写 |
| Chroma ingest | Chroma | 延后 | G4 |

---

## 3. P0：论文解析入库

代码：

```text
services/papers/pg_writes.py
services/search/ingest.py
services/search/online_downloader.py
```

现状：

```text
论文行 + sections/paragraphs/sentences
仍先写 SQLite
再由 outbox/PG 写入
```

目标：

```text
解析结果 -> PG transaction
失败回滚
不再写 SQLite
```

验收：

```text
新论文只写 PG
SQLite 行数不增长
outbox pending 0
```

---

## 4. P1：notes / claims / experiments

### notes

```text
services/notes/service.py
INSERT/UPDATE/DELETE notes
SQLite only
```

目标：

```text
notes 表迁 PG
```

### claims

```text
services/claims/pg_writes.py
services/claims/service.py
```

现状：

```text
PG 写 + SQLite 事件表/fallback
```

目标：

```text
claim_cards / events / evidence 全 PG
```

### experiments

```text
services/experiments/pg_writes.py
services/experiments/service.py
services/experiments/runs.py
```

现状：

```text
PG 写 + SQLite 运行/审计
```

目标：

```text
experiments / revisions / runs / audit 全 PG
```

---

## 5. P0：Outbox

代码：

```text
services/db/dual_write.py
```

现状：

```text
27 trigger
249 条历史事件
pending 0
```

目标：

```text
新写入不再产生 outbox
replay worker 停止
trigger 删除
outbox 表归档
```

验收：

```text
pending 持续 0
新写入不再增长
```

---

## 6. P2：data audit

```text
services/data_sandbox/audit.py
INSERT data_audit
SQLite only
```

目标：

```text
data_audit 迁 PG
```

---

## 7. 迁移顺序

```text
G3.2 论文解析入库 PG-only
G3.3 论文元数据更新 PG-only
G3.4 notes PG-only
G3.5 claims PG-only
G3.6 experiments PG-only
G3.7 data audit PG-only
G3.8 停 outbox
G3.9 删 trigger
G3.10 SQLite 只读归档
```

---

## 8. 每步验收

```text
1. 新写入只到 PG
2. SQLite 对应表行数不增长
3. outbox pending 不增长
4. 读取路径仍正常
5. 回滚开关存在
```

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 解析入库半写 | 数据不完整 | PG 单事务 |
| notes/claims 丢数据 | 用户数据 | 先双读校验 |
| outbox 历史未清 | 重复应用 | 归档后停 worker |
| 测试 fixture 依赖 SQLite | CI 失败 | 分批改 PG fixture |

---

## 10. 当前生产

```text
FTS       100% ParadeDB
Vector    Chroma
Anchor    关闭
Context   window=2
outbox    pending 0
app       healthy
```
