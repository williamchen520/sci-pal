# Phase 2：Online / Preprint 写路径

> 日期：2026-11-02  
> 状态：online paper/paragraph 与 preprint metadata 已写 PG；outbox 未收口。

## 1. Online downloader

`_import_new_papers`：

```text
if SCIPAL_PAPER_WRITE_BACKEND=postgres
  -> PG upsert paper
  -> SQLite INSERT OR REPLACE
  -> SQLite paragraphs
  -> PG replace_children(paragraphs, sentences=[])
```

注意：

```text
online 路径本来不写 sentences
replace_children 会删除该 paper 的 PG sentences
如果该 paper 之前有 sentences，需要重新生成
```

## 2. Preprint

`_patch_metadata`：

```text
SQLite UPDATE papers
-> PG update_metadata_if_exists
```

覆盖：

```text
year / doi
```

title/authors 仍只 SQLite。

## 3. 仍未迁移

```text
figures / tables
outbox
```

## 4. 风险

```text
online 的 replace_children 删除 sentences
preprint title/authors 未同步 PG
PG 失败为 best-effort，SQLite 保留
```

## 5. 代码

```text
services/search/online_downloader.py
services/search/preprint_ingest.py
services/papers/pg_writes.py
```

## 6. 测试

```text
full suite
```

## 7. 当前生产

```text
SCIPAL_PAPER_WRITE_BACKEND 未设置
```

## 8. 下一步

```text
1. 补 online/preprint 单测
2. outbox 收口
3. papers canary
```
