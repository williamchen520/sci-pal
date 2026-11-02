# Phase 2：Papers Ingest 写路径（第一片）

> 日期：2026-11-02  
> 状态：paper + children 已 fail-closed；online 仍 best-effort；outbox 未收口。

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

现在是 fail-closed：

```text
SQLite transaction 仍打开
-> PG 同一事务写 papers + paragraphs + sentences
-> 任一 PG 失败 -> PaperWriteError
-> SQLite context rollback
```

只有 SQLite commit 本身失败时才可能留下 PG orphan；这是剩余窗口。

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
PG 事务成功
-> SQLite commit 失败
-> PG 可能留下已提交的 paper/children
```

这是分布式提交无法完全消除的窗口；默认 flag 关闭，生产不触发。

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
