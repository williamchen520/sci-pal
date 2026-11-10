# P4b：只读语料切换

> 日期：2026-11-11  
> 状态：**检索层可切重建库；业务/身份仍走原库**

---

## 1. 为什么不是改 `SCIPAL_PG_DSN`

`scipal_rebuild` 只有语料：

```text
papers / paragraphs / sentences / embeddings
```

没有：

```text
users / workspaces / projects / experiments / notes
```

直接切 `SCIPAL_PG_DSN` 会导致：

```text
登录失败
项目/实验/笔记消失
```

## 2. 切法

新增：

```text
SCIPAL_PG_CORPUS_DSN
```

只让检索读它：

```text
PGVectorParagraphSearch
PGParagraphRetriever
SentenceHybridRetriever
evidence FTS fallback
```

业务 DSN 不变：

```text
SCIPAL_PG_DSN
SCIPAL_PG_MAIN_READ_DSN
SCIPAL_PG_ADMIN_DSN
```

## 3. 回滚

```text
删除 SCIPAL_PG_CORPUS_DSN
  -> corpus_connection() 回退 main_read
  -> 立即回旧语料
```

不需要改数据库。

## 4. 验证

本地：

```text
SCIPAL_PG_DSN=scipal_bench
SCIPAL_PG_CORPUS_DSN=scipal_rebuild
SentenceHybridRetriever -> evidence 3
```

生产部署后验证：

```text
/api/evidence/search -> 200
sentence_id 属于 paper_PMC...
```

## 5. 边界

```text
P4b 只切检索读
写入/ingest 仍走旧库
业务表仍在旧库
```

“旧库不用了”在这里准确表述是：

```text
旧语料不再被检索使用
不是旧业务库被删除
```
