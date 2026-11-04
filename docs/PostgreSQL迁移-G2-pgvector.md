# G2：pgvector 迁移报告（进行中）

> 日期：2026-11-04  
> 状态：G2.1–G2.4 完成；生产切换失败已回滚

## 1. 已完成

| 项 | 内容 | 状态 |
|---|---|---|
| G2.1 | `paragraph_embeddings` schema | ✅ |
| G2.2 | Chroma -> pgvector 回填脚本 | ✅ |
| G2.3 | `PGVectorParagraphSearch` | ✅ |
| G2.4 | 全量回填 | ✅ |
| G2.5 | 替换 Chroma 查询 | ⏳ |
| G2.6 | 关闭 Chroma | ⏳ |

## 2. Schema

```sql
CREATE TABLE paragraph_embeddings (
  para_id text PRIMARY KEY,
  paper_id text NOT NULL,
  embedding vector(768) NOT NULL,
  model text NOT NULL DEFAULT 'bge-base-en-v1.5',
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ... USING hnsw (embedding vector_cosine_ops);
```

文件：

```text
deploy/sql/001_paragraph_embeddings.sql
```

## 3. 数据源

```text
Chroma paragraphs_contextual
count 164,654
dimension 768
model bge-base-en-v1.5
```

## 4. 回填

```text
scripts/backfill_pg_embeddings.py
batch 5000
COPY paragraph_embeddings FROM STDIN
```

已验证：

```text
100 条 upsert OK
COPY 批量 OK
```

当前：

```text
164,654 / 164,654
无重复
vector(768)
```

## 5. 查询 adapter

```sql
SELECT ... 1 - (e.embedding <=> %s::vector) AS rank
FROM paragraph_embeddings e
JOIN paragraphs p USING (para_id)
ORDER BY e.embedding <=> %s::vector
LIMIT %s
```

实测：

```text
top1 rank 1.0
```

## 6. 测试

```text
tests.test_pg_vector 3 OK
全量 860 tests OK
```

## 7. G2.4 影子对比

96 题，向量单通道：

| 指标 | Chroma | pgvector |
|---|---:|---:|
| recall@10 | 0.6250 | 0.6146 |
| nDCG@10 | 0.4414 | 0.4357 |
| Jaccard | — | 0.925 |

HNSW：

```text
ef_search=100  recall .5729
ef_search=200  recall .6146
ef_search=500  recall .6146
```

## 7b. 生产切换结果

```text
生产 pgvector 96 题 recall .6250 / nDCG .4960
Chroma         96 题 recall .6875 / nDCG .5116
```

结论：

```text
生产集成未达标
已回滚 SCIPAL_VECTOR_BACKEND=chroma
G4 阻塞
```

## 8. 未完成

```text
HNSW 精确性调参 / 精确扫描对比
HybridSearch vector backend 切换
Chroma vs pgvector 灰度
关闭 Chroma
```

## 8. 生产

```text
向量仍走 Chroma
pgvector 未切流
```
