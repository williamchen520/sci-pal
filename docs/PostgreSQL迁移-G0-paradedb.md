# G0：ParadeDB 可行性报告

> 日期：2026-11-04  
> 结论：**G0 通过，可以进入 G1**

## 1. 环境

```text
PostgreSQL   18.6
pg_search    0.26.4
vector       0.8.6
容器         paradedb/paradedb:latest
端口         5434
```

## 2. 数据

```text
paragraphs   167,388
索引         paragraphs_bm25_idx
类型         bm25(para_id, text)
```

## 3. BM25 单通道（96 有效题）

```text
recall@10    0.6667
nDCG@10      0.4910
Jaccard      0.682
P95          0.183s
```

对比：

```text
SQLite FTS    0.66 / 0.50
PG native     0.20 / 0.41 / 4–6s
ParadeDB      0.67 / 0.49 / 0.18s
```

BM25 单通道 nDCG 略低于基线，但延迟极低、Jaccard 高。

## 4. BM25 + GPU rerank（96 题）

```text
recall@10    0.7500
nDCG@10      0.6203
```

对比当前生产基线：

```text
recall  0.6615
nDCG    0.5034
```

结论：

```text
BM25 候选 + GPU rerank 明显超过当前 SQLite 链路
q055 / q060 均恢复命中
```

## 5. G0 Gate

| 指标 | 门槛 | 实测 | 结果 |
|---|---:|---:|---|
| recall@10 | ≥0.6615 | 0.7500 | PASS |
| nDCG@10 | ≥0.5034 | 0.6203 | PASS |
| P95 | ≤2s | 0.183s（BM25） | PASS |

## 6. 结论

```text
原生 PG FTS：否决
ParadeDB BM25：通过
路线确定：G1 开始 BM25 生产适配
```

## 7. 风险 / 待验证

```text
1. summaries / sentences BM25 索引尚未建
2. 查询语法目前是简单 OR，需要 AND/短语/NEAR
3. 中文分词未验证
4. ParadeDB 容器版本/备份/升级流程
5. 生产 DSN 与扩展安装
```

## 8. 下一步 G1

```text
G1.1 PGParagraphBM25 adapter
G1.2 PGSummaryBM25
G1.3 PGSentenceBM25
G1.4 查询语法转换
G1.5 20/96 影子双跑
G1.6 灰度切换
```
