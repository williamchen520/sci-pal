# G1 工作总结：ParadeDB FTS 单栈迁移

> 日期：2026-11-04  
> 阶段：G1（FTS 适配与切流）  
> 结论：**G1 完成，生产 100% 走 ParadeDB BM25**

---

## 1. 目标

```text
用 ParadeDB pg_search BM25 替换 SQLite FTS5
保留 GPU reranker
不降低 96 题质量
可回退
```

---

## 2. 最终架构

```text
应用
  ├─ HybridSearch
  │    ├─ ParadeDB BM25（100%）
  │    └─ SQLite FTS5（仅回退）
  └─ GPU reranker

PostgreSQL 主库
  └─ papers / paragraphs / sentences / summaries

ParadeDB
  ├─ paragraphs_bm25_idx
  ├─ summaries_bm25_idx
  └─ sentences_bm25_idx
```

---

## 3. 阶段结果

| 阶段 | 内容 | 结果 |
|---|---|---|
| G0 | ParadeDB spike | BM25+GPU recall .75 / nDCG .620 |
| G1.1 | Paragraph BM25 | ✅ |
| G1.2 | Summary BM25 | ✅ |
| G1.3 | Sentence BM25 | ✅ |
| G1.4 | 短语 / AND / OR | ✅ |
| G1.5 | 96 题影子 | ✅ |
| G1.6 | 100% 灰度 | ✅ |

---

## 4. 数据与索引

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

扩展：

```text
PostgreSQL 18.6
pg_search  0.26.4
vector     0.8.6
```

---

## 5. 质量对比（96 题）

| FTS | recall@10 | nDCG@10 | MRR |
|---|---:|---:|---:|
| SQLite 100% | 0.6406 | 0.4989 | 0.4578 |
| ParadeDB 50% | 0.6771 | 0.5228 | 0.4760 |
| ParadeDB 100% | 0.6875 | 0.5116 | 0.4578 |

结论：

```text
100% recall 最高
50% nDCG 最高
为推进单轨选择 100%
```

G0 独立链路：

```text
BM25 + GPU rerank  recall .75 / nDCG .620
```

---

## 6. 查询能力

```text
普通关键词
"heart failure" 短语
AND
OR
paper_id / section_l1 / para_id 过滤
```

---

## 7. 灰度与回退

调度：

```text
zlib.crc32(query) % 100 < SCIPAL_FTS_PARADEDB_PERCENT
```

配置：

```text
SCIPAL_FTS_BACKEND=sqlite
SCIPAL_FTS_PARADEDB_PERCENT=100
SCIPAL_PARADEDB_DSN=...@paradedb:5432/scipal_g0
```

回退：

```text
ParadeDB 空结果/异常 -> SQLite
percent=0 -> 全 SQLite
```

---

## 8. 生产基础设施

```text
deploy-paradedb-1
  image: paradedb/paradedb:latest
  db: scipal_g0
  volume: paradedb_g0
  port: 5434
```

验证：

```text
app -> paradedb 可连接
paragraphs 167,388
```

---

## 9. 测试

```text
tests.test_pg_fts 12 OK
tests.test_hybrid_fts_routing 2 OK
全量 857 tests OK
```

---

## 10. 事故与修复

| 问题 | 修复 |
|---|---|
| entrypoint CRLF 导致 PROD 启不来 | LF + sed 去 `\\r` |
| ParadeDB PG18 数据路径冲突 | 挂 `/var/lib/postgresql` |
| `pg_search` 依赖 vector | 先 `CREATE EXTENSION vector` |
| q055/q060 被 rerank 挤出 | BM25 候选后恢复命中 |
| 导入耗时长 | pg_dump + 后台执行 |

---

## 11. 遗留技术债

按“零技术债”准则，G1 后仍有：

```text
1. SQLite FTS5 仍保留回退
2. native PG ts_rank 适配器仍存在
3. Summary / Sentence adapter 尚未接入应用主路径
4. FTS 在 ParadeDB，业务表在 scipal-pg，仍是两个 PG 实例
5. summaries/sentences 索引备份未纳入备份脚本
```

这些必须在 G4 前清理。

---

## 12. G1 Gate

| 条件 | 结果 |
|---|---|
| 96 题不低于基线 | ✅ .6875 > .6406 |
| 100% 灰度稳定 | ✅ |
| 回退开关可用 | ✅ |
| 857 tests | ✅ |
| 生产健康 | ✅ |

---

## 13. 结论

```text
G1 完成
SQLite FTS 退出主路径
ParadeDB BM25 接管 100%
GPU reranker 保持
```

下一步：

```text
G2 pgvector 替换 Chroma
G4 合并两个 PG 实例并删除 SQLite/native FTS
```
