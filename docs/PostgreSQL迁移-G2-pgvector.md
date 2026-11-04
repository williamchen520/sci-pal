# G2：pgvector 迁移报告（进行中）

> 日期：2026-11-04  
> 状态：G2.1–G2.3 完成，回填进行中

## 1. 已完成

| 项 | 内容 | 状态 |
|---|---|---|
| G2.1 | `paragraph_embeddings` schema | ✅ |
| G2.2 | Chroma -> pgvector 回填脚本 | ✅ |
| G2.3 | `PGVectorParagraphSearch` | ✅ |
| G2.4 | 全量回填 | 🟡 |
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
全量回填进行中
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

## 7. 未完成

```text
全量回填
Chroma vs pgvector recall 对比
HybridSearch vector backend 切换
关闭 Chroma
```

## 8. 生产

```text
向量仍走 Chroma
pgvector 未切流
```
