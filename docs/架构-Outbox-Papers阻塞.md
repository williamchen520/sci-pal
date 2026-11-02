# Papers 相关 Outbox 阻塞

> 日期：2026-11-02  
> 结论：papers / sections / paragraphs / sentences trigger **不能现在退役**。

## 1. 当前 trigger

```text
papers
sections
paragraphs
sentences
```

## 2. 已 PG-first 的路径

```text
JATS ingest
  paper row + paragraphs + sentences
  同一 PG 事务，失败回滚 SQLite

online downloader
  paper upsert PG-first
  paragraphs 仍是 commit 后 best-effort

preprint metadata
  year/doi best-effort
```

## 3. PDF / preprint 解析

`DatabaseWriter.insert_paper` 现在在 flag 开启时先写 PG：

```text
papers
paragraphs
figures
tables
```

然后才写 SQLite。

代码：

```text
services/papers/pg_writes.py  write_parsed_paper
build_db/db_writer.py         insert_paper
```

仍未 PG-first：

```text
citations / citation_mentions
parse_provenance
supplementary_files
```

### Watch delete / online

```text
watch placeholder delete 仍是 best-effort
online children 仍是 commit 后 best-effort
```

### watch placeholder delete

```text
watch/pg_writes.delete_paper_best_effort
  PG delete 失败时继续 SQLite
```

不是 fail-closed。

### build-time 脚本

```text
build_db/import_jats.py
build_db/build_sections_tree.py
build_db/build_sentences.py
build_db/db_writer.py
```

都是 SQLite 写入。

## 4. 结论

```text
JATS ingest 已接近收口
PDF/preprint 解析仍完全 SQLite
watch delete 不是 fail-closed
```

如果现在删 papers trigger：

```text
PDF/preprint 新论文不会进 PG
sections/paragraphs/sentences 也不会进 PG
```

所以不能删。

## 5. 退役前置条件

```text
1. DatabaseWriter 增加 PG 写路径
2. parse_service 走 PG 事务
3. online downloader children fail-closed
4. watch delete fail-closed
5. 连续 7 天 outbox pending=0 / drift=0
```

## 6. 当前决定

```text
papers/sections/paragraphs/sentences trigger 保留
不做“先删再补”
```

## 7. 下一步

```text
迁移 DatabaseWriter
  -> PDF/preprint PG-first
  -> 再评估 papers trigger
```
