# Worklog: PG FTS 适配器与影子对比

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

实现 PGParagraphFTS / PGSummaryFTS，并与 SQLite FTS 做影子对比。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
services/search/pg_fts.py
scripts/fts_shadow_compare.py
tests/test_pg_fts.py
docs/PostgreSQL迁移-FTS-shadow.json
docs/PostgreSQL迁移-FTS-shadow.md
docs/PostgreSQL迁移-FTS单栈盘点.md
docs/Research_Logs_Index.md
worklogs/2026-11-03-pg-fts-shadow.md
```

## 4. 业务逻辑变化

```text
新增 PGParagraphFTS
  paragraphs.search_vector
  ts_rank / ts_rank_cd
  paper_id / section_level1 过滤

新增 PGSummaryFTS
  summaries.search_vector
  top_k / paper_id

新增 fts_shadow_compare
  同一 query 分别跑 SQLite FTS5 和 PG
  输出 overlap / Jaccard
```

未改生产路由。

## 5. 影子对比（20 query，top-10）

```text
paragraph avg Jaccard  0.020
summary   avg Jaccard  0.242
```

典型：

```text
q001 paragraph common 0/10
q002 paragraph common 0/10
q004 paragraph common 3/10
q002 summary   common 7/10
```

结论：

```text
PG FTS 能返回结果
但 top-k 排序与 SQLite 差异很大
不能直接切
```

## 6. 性能

PG paragraph 查询：

```text
约 5–22 秒 / query（12 个 OR term）
```

原因：

```text
to_tsquery OR 命中集大
ts_rank_cd 需要对全部命中排序
```

SQLite 同 query 约 0.1–0.2 秒。

## 7. 测试

```text
tests.test_pg_fts 4 OK
全量 835 tests OK
```

## 8. 风险 / 外部 API

```text
无生产路由变化
PG 查询延迟不可接受
排序差异未解决
```

## 9. 未完成项

```text
PR Pending Review
PG query 性能优化
排序对齐 / 通道级切换
```
