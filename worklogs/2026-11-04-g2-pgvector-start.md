# Worklog: G2 pgvector 启动

> 日期：2026-11-04  
> PR：Pending Review

## 1. 已完成

```text
G2.1 paragraph_embeddings schema
G2.2 Chroma -> pgvector backfill 脚本
G2.3 PGVectorParagraphSearch adapter
```

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

## 3. 数据源

```text
Chroma paragraphs_contextual
count 164,654
dimension 768
```

## 4. 回填

```text
scripts/backfill_pg_embeddings.py
batch 1000
```

实测：

```text
100 条验证 OK
全量进行中
```

## 5. 查询

```sql
ORDER BY e.embedding <=> %s::vector
score = 1 - distance
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
G2.4 全量回填 + recall 对比
G2.5 替换 Chroma 查询
G2.6 关闭 Chroma
```
