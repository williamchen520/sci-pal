# 工作计划：SQLite → PostgreSQL 迁移

> 日期：2026-10-31  
> 状态：计划，不含迁移实现  
> 前置策略：[Benchmark PostgreSQL 策略](benchmark-PostgreSQL策略.md)  
> 最高原则：**原 SQLite 数据只能读，不能被迁移过程覆盖；任何阶段都必须可回退。**

---

## 1. 背景

SciPal 起步于个人单机使用，数据库是 SQLite：

```text
data/research.db
data/chroma/
```

现在支持多用户、项目、实验、watch、claim 和插件 benchmark，SQLite 的边界已经明确：

```text
写并发有限
长事务会阻塞
FTS5 与 PostgreSQL 语法不同
多 worker 下不可靠
```

目标不是“把连接串换掉”，而是：

```text
在不丢失现有数据的前提下，
分阶段把元数据与全文检索迁移到 PostgreSQL，
并保留可验证的回退路径。
```

---

## 2. 非目标

```text
不在本阶段迁移 Chroma（向量库继续独立）
不做跨机房/分片
不做 PostgreSQL RLS（后续）
不删除 SQLite 原始文件
不做一次性大爆炸切换
```

---

## 3. 数据安全红线

### 3.1 原库只读

迁移期间的任何脚本：

```text
不得对 data/research.db 执行 INSERT / UPDATE / DELETE / VACUUM / DROP
不得把 data/research.db 作为迁移目标
不得覆盖 data/research.db
```

迁移只在副本上操作：

```text
data/migration/research_snapshot.db
```

### 3.2 先备份，再迁移

每次迁移步骤开始前必须：

```text
1. VACUUM INTO 生成一致性快照
2. 复制到 backups/
3. PRAGMA integrity_check
4. 记录表行数与 sha256
5. 在 G 盘保留第二份
```

示例：

```powershell
python scripts\backup_sqlite.py
```

脚本行为：

```text
1. 只读打开源库（mode=ro）
2. VACUUM INTO 生成一致性快照
3. 对快照做 PRAGMA integrity_check
4. 统计 papers 行数
5. 计算 sha256
6. 拒绝覆盖已有快照
```

输出示例：

```json
{
  "source": "data/research.db",
  "dest": "backups/research_20261031_210616.db",
  "bytes": 1769127936,
  "source_integrity": "ok",
  "backup_integrity": "ok",
  "papers": 3310,
  "sha256": "..."
}
```

然后把快照复制到第二块盘：

```powershell
Copy-Item "D:\sciPal\backups\research_20261031_210616.db" `
  "G:\sciPal_deploy\backups\research_20261031_210616.db"
(Get-FileHash "G:\sciPal_deploy\backups\research_20261031_210616.db" -Algorithm SHA256).Hash
```

### 3.3 备份保留

```text
本地 backups/：至少 30 天
G:\sciPal_deploy\backups\：至少 30 天
每次 schema 变更前额外一份
```

### 3.4 回退原则

```text
任何阶段失败：停止，不回写 SQLite，直接切回原库。
SQLite 原库在整个迁移期间保持可启动。
只有 P6 验收通过后才允许标记为只读归档。
```

---

## 4. 现状审计

### 4.1 规模

```text
SQLite 调用点：约 600 处
表：约 70 张（含 FTS 影子表）
核心大表：
  papers       ~3,300
  paragraphs   ~167,000
  sentences    ~862,000
  citations    ~182,000
  sentence_links ~296,000
  paper_links  ~164,000
```

### 4.2 主要模块

```text
services/search/         FTS5 + Chroma + RRF
services/claims/         claim_cards / evidence / events
services/watch/          profiles / runs / items
services/projects/       projects / members
services/experiments/    experiments / runs / revisions
services/review/         综述项目 / 筛选 / 风险偏倚
services/notes/          笔记
services/tenancy/        users / workspaces / memberships
routes/*                 API 层直接 SQL
build_db/*               导入 / 结构重建
eval/*                   benchmark 读取
```

### 4.3 SQLite 特有依赖

| 依赖 | 迁移动作 |
|---|---|
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` |
| `AUTOINCREMENT` | `GENERATED ... AS IDENTITY` |
| `?` 占位符 | `%s` |
| `PRAGMA table_info` | `information_schema.columns` |
| `sqlite3.Row` | `psycopg.rows.dict_row` |
| `json_extract` | `jsonb ->` / `->>` |
| FTS5 `MATCH` / `bm25()` | `tsvector` + `websearch_to_tsquery` + `ts_rank_cd` |
| `VACUUM INTO` | `pg_dump` 快照 |
| `sqlite3.Connection.backup` | 不再使用 |

---

## 5. 目标架构

```text
Flask / services
  ↓
DBAdapter（新）
  ├─ SQLiteAdapter（现有，保留）
  └─ PostgresAdapter（新增）
        ↓
   PostgreSQL
     ├─ 元数据表
     ├─ 全文检索（tsvector + GIN）
     └─ 审计 / 任务
```

配置：

```text
SCIPAL_DB_BACKEND=sqlite | postgres
SCIPAL_PG_DSN=postgresql://...
SCIPAL_PG_POOL_MIN=1
SCIPAL_PG_POOL_MAX=10
```

原则：

```text
业务代码不直接依赖 psycopg
连接、事务、行工厂统一由 DBAdapter 提供
SQLite 路径保持可用，直到 P6
```

---

## 6. Schema 映射

### 6.1 核心表

| SQLite | PostgreSQL |
|---|---|
| `papers` | `papers` |
| `sections` | `sections` |
| `paragraphs` | `paragraphs` |
| `sentences` | `sentences` |
| `figures` / `tables` | `figures` / `tables` |
| `citations` | `citations` |
| `sentence_links` | `sentence_links` |
| `paper_links` | `paper_links` |
| `claim_cards` | `claim_cards` |
| `claim_card_evidence` | `claim_card_evidence` |
| `claim_card_events` | `claim_card_events` |
| `watch_*` | `watch_*` |
| `users` / `workspaces` / `memberships` | 同名 |
| `projects` / `experiments` / `experiment_runs` | 同名 |

### 6.2 类型

```text
TEXT       -> text
INTEGER    -> integer / bigint
REAL       -> double precision
JSON 字符串 -> jsonb（可选，先保留 text）
时间字符串  -> timestamptz（迁移时解析）
```

### 6.3 全文检索

SQLite：

```sql
SELECT ... FROM paragraphs_fts WHERE paragraphs_fts MATCH ? ORDER BY bm25(paragraphs_fts)
```

PostgreSQL：

```sql
ALTER TABLE paragraphs ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED;

CREATE INDEX paragraphs_search_idx ON paragraphs USING GIN (search_vector);

SELECT ... FROM paragraphs
WHERE search_vector @@ websearch_to_tsquery('english', %s)
ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) DESC;
```

需要替换：

```text
papers_fts
paragraphs_fts
sentences_fts
summaries_fts
```

中文内容需要额外方案：

```text
先保留原文；中文检索用 pg_trgm 或外部分词
不在 P1 解决
```

---

## 7. 分阶段实施

### P0：冻结与备份

```text
1. 记录当前版本、git commit、DB 行数
2. VACUUM INTO 快照
3. 双盘备份
4. integrity_check
5. 只读打开快照做一次抽样查询
```

验收：

```text
备份可打开
行数一致
核心查询结果一致
原库未被修改
```

### P1：Schema 与连接层

```text
1. 写 PostgreSQL schema DDL
2. 写 DBAdapter（连接/事务/行工厂）
3. 保持 SQLite 默认，不切换
4. 为 adapter 写单测
```

P1 实现（待合并）：

```text
build_db/postgres_schema.sql
build_db/generate_postgres_schema.py
services/db/adapter.py
services/db/__init__.py
tests/test_db_adapter.py
```

约束：

```text
默认 SCIPAL_DB_BACKEND=sqlite
PostgreSQL 需要 SCIPAL_PG_DSN + psycopg
本阶段不迁移数据
本阶段不切换读路径
连接池留到 P2
```

验收：

```text
SQLite 路径 699+ 测试仍通过
PostgreSQL schema 可生成
adapter 可连接/提交/回滚/关闭
schema 含核心表与 tsvector/GIN
```

### P2：只读 ETL

```text
1. 从 snapshot 读数据
2. COPY 批量写入 PostgreSQL
3. 记录每表行数、checksum
4. 不写回 SQLite
```

验收：

```text
行数一致
主键/外键抽样一致
核心检索 query 结果可比
```

P2 实现（待合并）：

```text
services/db/etl.py
scripts/pg_etl.py
tests/test_pg_etl.py
docs/PostgreSQL迁移-ETL-dryrun.json
docs/PostgreSQL迁移-ETL-checksum.json
docs/PostgreSQL迁移-ETL-verify.json
docs/PostgreSQL迁移-ETL-execute-citations.json
```

安全：

```text
assert_snapshot 拒绝 data/research.db
只读打开 snapshot
不写回 SQLite
```

执行结果（本地 PostgreSQL 16）：

```text
60 张表
expected_rows = 2,015,676
postgres_rows = 2,015,676
count_mismatches = 0
```

核心表逐行对比：

```text
papers       0 missing / 0 extra / 0 diff
paragraphs   0 missing / 0 extra / 0 diff
sentences    0 missing / 0 extra / 0 diff
citations    0 missing / 0 extra；year 类型转换为 TEXT，非 year 字段 diff 0
```

发现并修复：

```text
citations.year 含 'Feb 3, 2020' 这类自由文本；
PostgreSQL schema 改为 TEXT，避免 bigint 转换失败。
```

真实 COPY 已执行；源库仍是只读 snapshot。

### P3：影子读

```text
1. SCIPAL_READ_FROM_PG=0/1 开关
2. 同一 query 同时跑 SQLite / PG
3. 比较 top-k、计数、关键字段
4. 只记录差异，不改变线上读路径
```

验收：

```text
差异率在可解释范围
FTS 结果差异有清单
```

P3 实现（待合并）：

```text
services/db/shadow_read.py
scripts/shadow_read.py
tests/test_shadow_read.py
docs/PostgreSQL迁移-P3-shadow.json
```

执行结果（本地 PostgreSQL 16）：

```text
8 张核心表 key 全量对比：0 missing / 0 extra / 0 field diff
papers        3,310
paragraphs  167,388
sentences   862,677
claim_cards      10
claim_card_evidence 17
watch_items      11
users              1
workspaces         1
```

FTS 影子读：

| query | SQLite matches | PG matches | match Jaccard | top-10 common |
|---|---:|---:|---:|---:|
| hepatocellular carcinoma | 1,023 | 785 | 0.757 | 0 |
| immune checkpoint inhibitor | 321 | 786 | 0.326 | 1 |
| tumor microenvironment | 2,813 | 2,611 | 0.828 | 2 |

结论：

```text
表数据完全一致。
FTS 不是数据丢失，而是分词/词干差异：
  SQLite unicode61（无 stemming）
  PostgreSQL english（有 stemming）
```

排序也不同：

```text
SQLite 按 bm25
PostgreSQL 按 ts_rank_cd
```

因此 P3 结论：

```text
数据层可以继续 P4；
FTS 不能直接切换，需先统一 tokenizer/stemmer 或接受排序差异评审。
```

FTS 对齐实验：

```text
scripts/fts_alignment.py
docs/PostgreSQL迁移-FTS对齐实验.md
docs/PostgreSQL迁移-FTS对齐实验.json
```

结果：

```text
unicode61 vs english：平均 match Jaccard 0.637
porter    vs english：平均 match Jaccard 0.989
```

结论：

```text
porter + english 最接近；
但 20 query paper-level 测试显示 porter 不提升检索：
  unicode61 Recall@10 1.000
  porter    Recall@10 0.950
  PG english Recall@10 0.600
```

因此：

```text
FTS 暂不切换。
P4 只双写元数据表，FTS 继续走 SQLite unicode61。
```

Porter 重建与 20 query：

```text
scripts/rebuild_fts_porter.py
scripts/fts_porter_compare.py
docs/PostgreSQL迁移-FTS-porter-20query.md
docs/PostgreSQL迁移-FTS-porter-20query.json
docs/PostgreSQL迁移-FTS-porter-rebuild.json
```

### P4：双写

```text
1. SQLite 仍为主
2. 写 SQLite 成功后，异步写 PostgreSQL
3. 失败进入 replay queue
4. 记录 lag
```

验收：

```text
连续 24h 无未解释 lag
回放可补齐
回退只需停双写，SQLite 仍完整
```

### P5：切换

```text
1. 短写冻结
2. 确认 PG lag=0
3. SCIPAL_DB_BACKEND=postgres
4. 观察 24–72h
5. 保留 SQLite 只读
```

回退：

```text
SCIPAL_DB_BACKEND=sqlite
停止 PG 写入
用 P4 的 replay/反向导出补齐 SQLite
```

验收：

```text
读路径正常
写路径正常
并发测试通过
回退演练成功
```

### P6：归档

```text
1. 连续 30 天无回退
2. SQLite 标记 archive，不再写
3. 保留至少两份异地备份
4. 更新 README / 架构图
```

---

## 8. 验证清单

### 8.1 数据

```text
papers 行数
paragraphs 行数
sentences 行数
citations 行数
claim_cards / evidence
watch_items
users / workspaces
```

### 8.2 查询

```text
1 个精确标题查询
1 个作者查询
1 个 FTS 关键词查询
1 个 claim 检索
1 个 workspace 隔离查询
1 个 watch profile 查询
```

### 8.3 并发

```text
按 Benchmark PostgreSQL 策略
只在 PostgreSQL 上跑 >100 篇/并发测试
SQLite 只允许小规模本地验证
```

---

## 9. 风险

| 风险 | 缓解 |
|---|---|
| 迁移脚本误写原库 | 原库 chmod/只读；脚本只接受 snapshot 路径 |
| FTS 结果漂移 | P3 影子读 + 差异清单 |
| 双写 lag | replay queue + 24h 观察 |
| 回退丢写 | 保留 SQLite 双写窗口；切换后短期双写 |
| 长事务/锁 | 连接池 + 批大小 + 超时 |
| 中文检索退化 | 先保留原文；pg_trgm / 外部分词单独评估 |
| Chroma 与 PG 不一致 | paper_id 稳定；Chroma 不迁移 |
| 备份被覆盖 | 时间戳命名 + 双盘 + 30 天保留 |

---

## 10. 验收标准

```text
1. 原 research.db 从未被迁移脚本写入
2. 每次迁移前有可打开、integrity_check=ok 的备份
3. SQLite 路径在 P1–P3 持续可用
4. PG 与 SQLite 核心查询差异有清单
5. 双写 24h 无未解释 lag
6. 切换后 72h 无 P0/P1 故障
7. 回退演练成功
8. 692+ 测试通过（迁移期间不下降）
9. benchmark 大规模/并发只在 PG 上跑
```

---

## 11. 时间估算

```text
P0 备份/审计        1 天
P1 schema/adapter   3–5 天
P2 只读 ETL         3–5 天
P3 影子读           3–5 天
P4 双写             3–5 天
P5 切换/观察        3–7 天
P6 归档             30 天观察
```

不要压缩 P0 和 P5。

---

## 12. 第一件事

在写任何迁移代码前，先做：

```text
1. 生成 snapshot
2. 双盘备份
3. integrity_check
4. 行数清单
5. 把清单写入 docs/PostgreSQL迁移-基线.md
```

没有这份基线，不开始 P1。
