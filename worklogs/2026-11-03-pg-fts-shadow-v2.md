# Worklog: PG FTS 影子对比 v2

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

v1 只比 top-k，无法区分“召回差”和“排序差”；且 12 个 OR term 太慢。

## 2. 修改

```text
scripts/fts_shadow_compare.py
  --term-limit 6
  --ranker rank
  增加 sqlite_top_in_pg_match
  输出 match recall
```

PG 适配器本身未改。

## 3. v2 结果（20 query，top-10）

```text
paragraph Jaccard       0.109
paragraph match recall  0.975
summary   Jaccard       0.313
summary   match recall  1.000
```

结论：

```text
SQLite top-10 有 97.5% 落在 PG 命中集
PG 召回基本没问题
主要差距是 ranking
```

## 4. 延迟

```text
q001 3.5s
q002 16.3s
q003 9.6s
```

仍不可接受。

## 5. 测试

```text
全量 835 tests OK（上一轮）
本次仅脚本参数/报告变更
```

## 6. 风险 / 外部 API

```text
无生产路由变化
PG FTS 仍只用于影子对比
```

## 7. 未完成项

```text
PR Pending Review
ranking 对齐
PG FTS 查询性能
```
