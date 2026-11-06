# PostgreSQL SQL 提取与方言解析

> 日期：2026-11-06  
> 输入：`scripts/pg_sql_extract.py`  
> 输出：`eval/results/pg_sql_extract.json`  
> 性质：只读分析，不改业务代码

---

## 1. 总结

提取 SQL 字符串：

```text
1,304 条
```

sqlglot 分类：

| 分类 | 数量 | 含义 |
|---|---:|---|
| portable | 1,120 | SQLite/PG 都能解析 |
| sqlite_only | 20 | 仅 SQLite 解析 |
| postgres_only | 27 | 仅 PG 解析 |
| unparsed | 137 | 动态 SQL / f-string / 文档字符串误报 |

关键结论：

```text
绝大多数 SQL 语法可移植
真正的风险不是“解析失败”
而是“两边都能解析，但语义不同”
```

例如：

```sql
INSERT OR REPLACE
LIKE
?
lastrowid
```

sqlglot 的 PG 解析器也能接受 `INSERT OR REPLACE`，所以不能只靠解析器判断方言。

---

## 2. sqlite_only：20 条

全部是 SQLite FTS5：

```text
MATCH
bm25()
rowid
```

运行时命中：

```text
services/search/hybrid_search.py:414/422
services/search/sentence_seeds.py:34
services/search/summary_search.py:34
services/search/abstract_search.py:80
services/claims/service.py:263
services/quality/guard.py:115
services/review/title_recall.py:34/108
services/db/shadow_read.py:198/210
```

脚本/插件：

```text
scripts/fts_alignment.py
scripts/fts_sentence_compare.py
scripts/sentence_20_query.py
scripts/soft_cap_mmr_audit.py
plugins/adapters/retriever_bm25.py
eval/scifact_benchmark.py
```

### 风险

```text
生产 FTS 已 100% ParadeDB
但这些 SQLite FTS fallback 仍在
一旦 PG FTS 未命中/异常，可能回落到 SQLite FTS
```

### 重点

```text
services/search/hybrid_search.py
```

同一文件里既有 ParadeDB 路径，也有：

```python
FROM paragraphs_fts
bm25(paragraphs_fts)
```

这类 fallback 必须在 PG-only 后禁用或删除，否则：

```text
SQLite 不能只读
两套排序结果不一致
```

---

## 3. postgres_only：27 条

主要是：

```text
pgvector
tsquery / ts_rank_cd
unnest
ON CONFLICT
RETURNING
```

这些是 PG 目标路径，正常。

文件：

```text
services/claims/pg_search.py
services/claims/pg_writes.py
services/experiments/pg_write.py
services/experiments/pg_writes.py
services/papers/pg_writes.py
services/protocols/pg_import.py
services/protocols/pg_runs.py
services/review/pg_writes.py
services/search/pg_fts.py
services/watch/pg_writes.py
scripts/fts_porter_compare.py
scripts/g4_backfill_embeddings.py
```

需要确认：

```text
这些 SQL 只在 PG 连接上执行
不会被 SQLite conn 误用
```

---

## 4. unparsed：137 条

主要来源：

```text
f-string 动态表名/列名
SQL 片段拼接
docstring 被误识别
正则字符串
```

典型：

```text
build_db/db_writer.py:42
  "Insert a complete parsed paper into the database..."
  -> 文档字符串，非 SQL

build_db/build_communities.py:168
  "SELECT keywords FROM papers WHERE paper_id IN ("
  -> 拼接片段

api_server.py:711
  "UPDATE tasks ... error=? ..."
  -> 动态 SQL
```

处理方式：

```text
先排除 docstring
再对 f-string 做参数化模板
最后人工看剩余
```

---

## 5. 解析器抓不到、但真实存在的语义问题

### 5.1 `INSERT OR REPLACE`

例如：

```text
services/claims/service.py:125
services/protocols/service.py:221
services/review/review_repository.py:100
services/review/systematic.py:117/136
services/search/ingest.py:365/414/438
services/search/online_downloader.py:585/608
services/tenancy/service.py:193/204/208/408
services/trust/retraction.py:69
services/watch/repo.py:136/151/328
services/watch/runner.py:97
```

这些多数是 fallback，但：

```text
fallback 一旦触发
PG 连接执行会报语法错误
```

### 5.2 `?` 占位符

`pg_*.py` 中出现 `?` 的位置：

```text
services/papers/pg_writes.py:68/110/465-475
services/watch/pg_writes.py:71
build_db/pg_v2_import_pdf.py:56
```

这些不是 PG SQL，而是：

```text
PG-first + SQLite mirror 分支
```

在 `pg_only()` 为真时不会执行；但：

```text
代码结构仍允许回退
```

### 5.3 `LIKE`

提取到的 SQL 中：

```text
services/protocols/service.py:279/301
routes/abstracts.py:29/40
services/query/search_service.py:54/86/118-121/151-153
services/search/hybrid_search.py:149/458
```

SQLite 大小写不敏感，PG 敏感。

`hybrid_search.py:458` 的 `journal LIKE ?` 尤其重要：

```text
它仍使用 SQLite 连接
```

---

## 6. 运行时优先级

| 路径 | 问题 | 级别 |
|---|---|---|
| tasks | 无 queued/claim | P0 |
| webhooks | 写 SQLite + lastrowid | P0 |
| hybrid_search SQLite FTS | 可能 fallback | P1 |
| protocols/abstracts LIKE | 大小写 | P1 |
| `INSERT OR` fallback | 触发即 500 | P1 |
| pg_*.py `?` mirror | 结构可回退 | P1 |
| FTS5 scripts | 只影响脚本 | P2 |

---

## 7. 下一步

### 7.1 先做排除

```text
排除 docstring
排除纯路径 glob
排除测试/脚本
```

得到“运行时 SQL 清单”。

### 7.2 再做语义规则

```text
LIKE 无 lower/ILIKE
INSERT OR
lastrowid
? 占位符
空字符串类型
```

### 7.3 最后做真实 SQL 捕获

staging：

```text
log_statement=all
```

跑 API smoke，比对实际执行 SQL。

---

## 8. 结论

```text
语法层面：大部分可移植
语义层面：仍有一批 SQLite 思维
结构层面：fallback 仍可回到 SQLite
```

所以下一步不是改 SQL 方言，而是：

```text
先把运行时可达路径收敛
再逐条修 P0/P1
```
