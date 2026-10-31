# P4 元数据双写

> 日期：2026-11-01  
> 原则：SQLite 仍是主库；PostgreSQL 只做影子；**FTS 不双写、不切换**。

---

## 1. 设计

```text
业务写 SQLite
  ↓
AFTER INSERT/UPDATE/DELETE 触发器
  ↓
dual_write_outbox（SQLite）
  ↓
replay worker
  ↓
PostgreSQL upsert / delete
```

关键点：

```text
业务写入不等待 PostgreSQL
PG 失败只记录 outbox.last_error，不影响 SQLite
回退只需停止 replay + 不切读路径
```

明确不做：

```text
不双写 FTS
不切换生产读路径
不自动删除 SQLite 数据
```

---

## 2. 覆盖范围

默认 21 张元数据表：

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
claim_cards
claim_card_evidence
claim_card_events
watch_items
watch_profiles
watch_runs
watch_seen
users
workspaces
memberships
review_projects
review_events
```

每张表：

```text
3 个触发器：INSERT / UPDATE / DELETE
```

当前：

```text
63 个触发器
0 个 FTS 触发器
```

---

## 3. Outbox

表：

```sql
dual_write_outbox (
  id, table_name, op, key_json,
  created_at, processed_at, attempts, last_error
)
```

`key_json` 示例：

```json
{"paper_id": "paper_PMC12707946_2d3bcc67"}
```

复合主键：

```json
{"workspace_id": "ws_default", "user_id": "user_local"}
```

语义：

```text
op = upsert / delete
key_json = 只存主键，不存整行
replay 时再回 SQLite 取当前行
```

好处：

```text
同一行多次更新可以合并为最后一次状态
不会把旧值复制到 PG
```

---

## 4. 安装

```powershell
python scripts\setup_dual_write.py --apply
```

行为：

```text
1. 先 create_backup 到 backups/
2. 创建 dual_write_outbox
3. 安装 21 张表的 63 个触发器
4. PRAGMA integrity_check
```

本次安装：

```text
backup: data/backups/research_20261101_012330.db
outbox pending: 0
integrity: ok
```

脚本默认 **dry-run**；只有显式 `--apply` 才改库。

---

## 5. 回放

```powershell
$env:SCIPAL_PG_DSN = "postgresql://..."

python scripts\replay_dual_write.py
```

常驻：

```powershell
python scripts\replay_dual_write.py --loop --interval 10
```

输出：

```json
{"selected": 1, "applied": 1, "failed": 0, "pending": 0, "oldest_pending": null}
```

真实 PG 验证：

```text
手动 enqueue 1 条已存在 paper 的 upsert
replay applied=1 failed=0
未改变业务数据
```

---

## 6. 回退

```text
1. 停止 replay worker
2. 不切换读路径
3. SQLite 仍是完整主库
4. 如需清理：drop dual_write_outbox + dualwrite_* 触发器
```

不需要恢复数据库；数据始终在 SQLite。

---

## 7. 健康检查

```powershell
python scripts\dual_write_healthcheck.py
```

检查：

```text
pending / failed / oldest_pending
pending_age_seconds
63 个触发器
21 张表 SQLite vs PG 行数
mismatches
```

本次：

```text
pending 0
failed 0
triggers 63
mismatches []
status ok
```

报告：

```text
docs/PostgreSQL迁移-P4-health.json
```

---

## 8. 测试

```text
tests/test_dual_write.py
  - 只给元数据表装触发器
  - insert/update/delete 入 outbox
  - 复合主键
  - fake PG upsert/delete
  - citations.year 转字符串
```

全量：

```text
732 tests OK
```

---

## 8. Staging soak

脚本：

```text
scripts/p4_staging_soak.py
```

隔离环境：

```text
SQLite: backups/soak.sqlite
PG:     scipal_dualwrite_soak
```

流程：

```text
1. 复制 snapshot
2. 安装 21 表触发器
3. 建 staging PG + P1 schema
4. 先把 4 张基线表 COPY 到 staging
5. 执行 500 cycles 写入/更新/删除
6. replay 全部 outbox
7. 对比 SQLite / PG 行数
```

结果：

```text
operations   2,422
applied      2,422
failed       0
pending      0
replay       17.3s
total        154.1s
mismatches   []
status       ok
```

行数：

| table | SQLite | PG |
|---|---:|---:|
| papers | 3,710 | 3,710 |
| claim_cards | 438 | 438 |
| watch_items | 511 | 511 |
| memberships | 501 | 501 |

结论：

```text
双写触发器 + replay + upsert 在隔离环境通过。
没有等待 24h 墙钟；用 2,422 次真实写入替代。
```

---

## 9. 限制

```text
1. 24h 观察被 staging soak 替代；真实线上流量仍未长时间验证
2. replay 是 at-least-once；PG 侧 upsert 幂等
3. 只覆盖 21 张核心元数据表，不是全部 60 张
4. FTS 明确不双写
5. 主键更新会产生旧行残留；当前假定主键不变
6. 触发器会增加 SQLite 写入开销（小，但需压测）
```

---

## 10. 相关文件

```text
services/db/dual_write.py
scripts/setup_dual_write.py
scripts/replay_dual_write.py
tests/test_dual_write.py
docs/PostgreSQL迁移-P4-dualwrite-setup.json
```
