# Worklog: PG FTS 延迟实验（2s 目标）

> 日期：2026-11-04  
> PR：Pending Review

## 1. 需求

把 PG+rerank 从 5.8s 压到 2s 级，同时不能明显低于 SQLite。

## 2. 实验

```text
term 4 / candidates 100   5.79s   nDCG .501
term 3 / candidates 50    4.16s   nDCG .623（20 query）
term 2 / candidates 50    2.74s   nDCG .513（20 query）
```

对照：

```text
SQLite 20 query nDCG .532
```

## 3. 结论

```text
term2 达到 2.7s，但 nDCG .513 < SQLite .532
term3 nDCG .623，但 4.16s
2s + 质量 目前不可兼得
```

延迟下限：

```text
PG 查询 1.3–2.7s
rerank 1.4s
```

## 4. 选项

### A. 接受 3–4s

```text
term3 + candidates 50
nDCG .623
4.16s
```

### B. 用 SQLite 做候选召回

```text
SQLite FTS 0.1–0.2s
PG 只做元数据/rerank
但 FTS 不再是 PG 单栈
```

### C. 外部搜索引擎

```text
Elasticsearch / OpenSearch / ParadeDB
才能同时做到 1s + BM25 排序
```

## 5. 建议

```text
如果目标严格 2s：不能继续用当前 PG ts_rank 方案
如果接受 3–4s：term3 + rerank 可用
如果坚持 PG 单栈：需要引入 ParadeDB / RUM 或专用 FTS
```

## 6. 测试

```text
全量 841 tests OK
```

## 7. 未完成项

```text
PR Pending Review
架构选择
```
