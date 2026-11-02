# Phase 2：Papers Ingest 写路径（第一片）

> 日期：2026-11-02  
> 状态：paper row + paragraph/sentence batch 已写 PG；figures/tables/outbox 未收口。

## 1. 已迁移

`services/search/ingest.py` 在写 SQLite 之前：

```text
if SCIPAL_PAPER_WRITE_BACKEND=postgres
  -> PG upsert papers
  -> SQLite INSERT OR REPLACE
```

upsert 内容：

```text
paper_id / filename / title / abstract / authors
journal / year / doi
```

## 2. 代码

```text
services/papers/pg_writes.py    upsert_paper
services/search/ingest.py       _write_batch
```

## 3. Paragraph / Sentence batch

SQLite batch commit 后：

```text
if SCIPAL_PAPER_WRITE_BACKEND=postgres
  -> DELETE PG sentences/paragraphs for paper
  -> INSERT paragraphs
  -> INSERT sentences
  -> to_tsvector('english', text)
```

代码：

```text
services/papers/pg_writes.py  replace_children
services/search/ingest.py     children collection
```

这是 best-effort：PG 失败会 warning，SQLite 结果保留，outbox 仍是修复路径。

## 4. 仍未迁移

```text
figures / tables
online_downloader paper inserts
preprint_ingest metadata updates
```

这些仍 SQLite + outbox。

因此：

```text
paper + paragraph + sentence 已写 PG
完整 ingest 仍不是 PG-primary
outbox 不能删
```

## 5. 风险

```text
PG upsert 成功后 SQLite batch 失败
-> PG 可能留下无 children 的 paper
```

这是当前切片的已知窗口；默认 flag 关闭，生产不触发。

## 6. 测试

```text
tests.test_ingest  11 tests OK
```

## 7. 当前生产

```text
SCIPAL_PAPER_WRITE_BACKEND 未设置
```

## 8. 下一步

```text
1. paragraphs/sentences PG batch writer
2. online_downloader / preprint_ingest
3. 停 papers outbox
4. 观察 drift
```
