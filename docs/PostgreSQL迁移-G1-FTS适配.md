# G1：ParadeDB FTS 适配报告

> 日期：2026-11-04  
> 状态：G1.1–G1.3 完成，生产未切换

## 1. 已完成

| 项 | 内容 | 状态 |
|---|---|---|
| G1.1 | `ParadeDBParagraphFTS` | ✅ |
| G1.2 | `ParadeDBSummaryFTS` | ✅ |
| G1.3 | `ParadeDBSentenceFTS` | ✅ |
| G1.4 | AND / 短语查询 | ✅ |
| G1.5 | 20/96 影子双跑 | ✅ |
| G1.6 | 10% 灰度 | 🟡 进行中 |

## 2. 数据

```text
paragraphs   167,388
summaries     69,128
sentences    862,677
```

索引：

```text
paragraphs_bm25_idx  bm25(para_id, text)
summaries_bm25_idx   bm25(summary_id, title, text)
sentences_bm25_idx   bm25(sentence_id, text)
```

## 3. 查询接口

段落：

```text
p.text @@@ query
ORDER BY pdb.score(p.para_id) DESC
```

摘要：

```text
(s.title @@@ query OR s.text @@@ query)
ORDER BY pdb.score(s.summary_id) DESC
```

句子：

```text
s.text @@@ query
ORDER BY pdb.score(s.sentence_id) DESC
```

## 4. 实测

| 类型 | 热延迟 | 结果 |
|---|---:|---|
| paragraphs | ~0.1s | 10 hits |
| summaries | 1.35s（首次） | 3 hits |
| sentences | 0.35s（首次） | 3 hits |

## 5. 开关

```text
SCIPAL_FTS_BACKEND=sqlite      默认
SCIPAL_FTS_BACKEND=paradedb    BM25
SCIPAL_FTS_BACKEND=postgres    native PG（否决）
```

DSN：

```text
SCIPAL_PARADEDB_DSN
```

## 6. 测试

```text
tests.test_pg_fts 10 OK
全量 853 tests OK
```

## 7. 查询语法

```text
"heart failure"       -> 短语
any                   -> OR
all                   -> AND
```

实测：

```text
"hepatocellular carcinoma" immune checkpoint  -> 3 hits
"hepatocellular carcinoma" AND immune         -> 3 hits
```

## 8. G1.5 影子双跑

代码路径：

```text
ParadeDBParagraphFTS.search(top_k=50)
  -> GPU reranker
  -> top10
```

96 题：

```text
recall@10   0.7500
nDCG@10     0.6203
```

对比生产：

```text
recall  0.6615
nDCG    0.5034
```

结论：

```text
ParadeDB 全链路超过当前 SQLite 链路
```

## 9. G1.6 灰度

生产配置：

```text
SCIPAL_FTS_BACKEND=sqlite
SCIPAL_FTS_PARADEDB_PERCENT=10
SCIPAL_PARADEDB_DSN=...@paradedb:5432/scipal_g0
```

调度：

```text
zlib.crc32(query) % 100 < percent
```

回退：

```text
ParadeDB 空结果/异常 -> SQLite
percent=0 -> 全 SQLite
```

实测：

```text
pancreatic cancer (bucket 0)  12.6s（冷）
tumor microenvironment (bucket 2) 5.6s
```

## 10. 未完成

```text
24h 观察
10% -> 50% -> 100%
删除 native PG FTS 旧路径（G4）
```

## 8. 原则

```text
所有 FTS 只保留 ParadeDB 一条目标路径
native PG ts_rank 不再扩展
SQLite 仅作为回退，G5 前不删除
```
