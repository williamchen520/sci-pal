# 文档 RAG（独立库）

> 2026-11-12 · `scipal_docs.docs_rag`  
> **独立于 `scipal_core` / `scipal_rebuild`**，不共用连接、表、索引。

---

## 1. 边界

```text
数据库     scipal_docs
schema     docs_rag
embedding  bge-small-zh-v1.5 (512-dim)
索引       HNSW + pg_trgm + GIN simple FTS
```

禁止：

```text
不在 scipal_rebuild 建 docs 表
不共用 paragraph_embeddings
不通过 corpus_connection() 访问 docs
不做跨库外键
```

---

## 2. 当前规模

```text
documents   438
chunks      5,885
embeddings  5,885
数据库大小   59 MB
```

切分方式：

```text
heading-aware
按段落优先
超长段才做句子窗口，200 字符重叠
不做 500 词硬切
```

---

## 3. 建库

```bash
# 1. 创建独立数据库和角色（由管理员执行）
# 2. 在 scipal_docs 中执行 schema.sql
psql "$SCIPAL_DOCS_DSN" -f docs_rag/schema.sql
```

环境变量：

```text
SCIPAL_DOCS_DSN        owner，写入/建索引
SCIPAL_DOCS_READ_DSN   reader，只读检索
SCIPAL_DOCS_EMBED_MODEL 默认 G:/models/bge-small-zh-v1.5
SCIPAL_DOCS_DEVICE     cuda 或 cpu
```

不要把真实 DSN 写入仓库；本地参考 `G:/runs/docs_rag.env`（不在 git 内）。

---

## 4. 灌库

```bash
python -m docs_rag.ingest
```

输出：

```text
DOCS_RAG_INGEST_OK docs=438 chunks=5885 dim=512
```

增量：

```text
按 path upsert
重新灌某篇时先删该 doc 的 chunks，级联删 embeddings
```

---

## 5. 检索

```bash
python -m docs_rag.search "core 和 rebuild 为什么要物理隔离" --top-k 8
```

融合：

```text
pgvector HNSW
pg_trgm similarity + word_similarity（正文/标题）
RRF
```

返回字段：

```text
chunk_id / doc_id / heading / text
path / title / category / score
```

---

## 6. 基线评测

查询集：

```text
docs_rag/eval_queries.json
```

12 条人工问题，按“正确文档出现在前 k 个 chunk”计：

| 指标 | 值 |
|---|---:|
| Hit@1 | 0.583 |
| Hit@5 | 0.917 |
| Hit@10 | 1.000 |
| MRR@10 | 0.713 |

注意：

```text
这是内部小查询集，不是 SciFact/QASPER 公开 benchmark
只评检索，不评答案生成
```

失败样例：

```text
"内部 ingest 和 embed 端点需要什么 token"
  正确文档 P6-红队审计 排第 1（已修正 gold）
"当前总共有多少 route 和 method"
  架构与路由全景图 排第 2
```

---

## 7. 已知限制

```text
中文 embedding 是 512 维小模型，长文档语义上限有限
chunk 1,600 字符，仍可能截断关键表格
pg_trgm 对中文短语是字符级近似，不是分词
没有 query rewrite / rerank
没有答案生成与引用校验
```

---

## 8. 下一步

```text
1. 用 30–50 条真实问题替换 12 条小集
2. 比较 vector-only / lexical-only / hybrid
3. 评估 chunk 大小 800 / 1200 / 1600
4. 需要答案时再接 LLM，但仍只读 scipal_docs
```
