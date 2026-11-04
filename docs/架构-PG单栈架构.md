# SciPal PostgreSQL 单栈架构（G2 决策）

> 日期：2026-11-04  
> 状态：pgvector 混合链路验证通过，成为向量主引擎

## 1. 结论

```text
pgvector 是目标主引擎
离线混合链路达标（recall .7604 / nDCG .6134）
但生产集成仅 .6250 / .4960，低于 Chroma .6875 / .5116
因此 Chroma 暂不能删除，G4 阻塞
```

## 2. 全链路对比（96 题）

| 链路 | recall@10 | nDCG@10 |
|---|---:|---:|
| SQLite FTS + Chroma + rerank（旧） | 0.6406 | 0.4989 |
| ParadeDB BM25 + Chroma + rerank | 0.6875 | 0.5116 |
| ParadeDB BM25 + pgvector + GPU rerank（离线） | 0.7604 | 0.6134 |
| ParadeDB BM25 + pgvector + rerank（生产） | 0.6250 | 0.4960 |

## 3. 向量单通道对比

| 指标 | Chroma | pgvector |
|---|---:|---:|
| recall@10 | 0.6250 | 0.6146 |
| nDCG@10 | 0.4414 | 0.4357 |
| Jaccard | — | 0.925 |

HNSW：

```text
ef_search=200（固定）
```

判断：

```text
单通道差 1%
Jaccard 92.5%
混合链路反超
```

## 4. 目标架构

```text
PostgreSQL
  ├─ 业务表
  ├─ ParadeDB BM25
  │    paragraphs / summaries / sentences
  ├─ pgvector
  │    paragraph_embeddings
  └─ HNSW

应用
  ├─ HybridSearch
  ├─ GPU reranker
  └─ 只连 PostgreSQL

退役
  ├─ Chroma
  ├─ SQLite FTS5
  └─ native PG ts_rank
```

## 5. 数据

```text
paragraph_embeddings 164,654
vector(768)
HNSW cosine
```

## 6. 迁移状态

```text
FTS       ParadeDB 100%
Vector    生产 Chroma，pgvector 离线通过
Chroma    保留
SQLite    保留
G4        阻塞
```

## 7. G4 删除边界

G4 不能只删 `chromadb` import，必须按集合逐个替换：

```text
paragraphs_contextual  -> paragraph_embeddings  已完成
summaries              -> summary_embeddings    待做
sentences              -> sentence_embeddings   待做
papers                 -> paper_embeddings      待做
figures                -> figure_embeddings     待做
tables                 -> table_embeddings      待做
chunks                 -> chunk_embeddings      待做
abstracts              -> abstract_embeddings   待做
```

每删一个 collection，必须同步删除：

```text
读取代码
写入/ingest 代码
测试 fixture
备份/恢复
```

## 8. 原则

```text
单轨运行
零技术债
长期维护成本最低
```

不允许长期保留“pgvector 为主、Chroma 并行”的双读。
