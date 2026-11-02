# Build / Ingest 脚本盘点

> 日期：2026-11-02  
> 结论：`import_jats` 不是纯 build 脚本，它在 Europe PMC 运行时被调用。

## 1. 运行时实际使用

### import_jats

```text
services/search/europe_pmc.py
  from build_db.import_jats import import_file
```

用途：

```text
Europe PMC 全文 JATS 导入
```

写入：

```text
papers
sections
paragraphs
sentences
figures
tables
citations
sentence_links
```

结论：

```text
import_jats 是运行时路径
不是 legacy build 工具
```

现在 `import_file` 在返回前调用：

```text
services.papers.pg_writes.sync_paper_graph
```

把 papers/sections/paragraphs/sentences/figures/tables/citations/sentence_links
镜像到 PG。

如果 PG 失败：

```text
import_file 抛 PaperWriteError
调用方不 commit，SQLite 回滚
```

### parse_service / DatabaseWriter

```text
routes/papers_actions.py
services/search/preprint_ingest.py
  -> build_db.parse_service.parse_and_store
  -> build_db.db_writer.DatabaseWriter
```

用途：

```text
PDF / preprint 解析入库
```

### build_sections_tree

```text
build_db/build_sections_tree.py
  build_for_paper(...)
```

用于从 paragraphs 重建 sections / section_id，属于离线构建。

### build_sentences

```text
build_db/build_sentences.py
```

用于 DROP/重建 SQLite sentences，属于离线构建。

## 2. 纯离线 / legacy

```text
build_db/build_database.py   全库重跑
build_db/build_xml_db.py     XML 全库重跑
build_db/build_fts.py        FTS 重建
build_db/import_jats.py      import_file 运行时；其余部分可复用
```

## 3. 对 trigger 的影响

```text
import_jats.import_file 仍写 SQLite
  -> papers/sections/paragraphs/sentences trigger 仍需要
```

因此不能因为“build_sections/build_sentences 已 PG-first”就删 trigger。

## 4. 优先顺序

```text
1. import_jats.import_file PG-first
2. sentence_links / citations PG-first
3. 其他 build 脚本标记 legacy
4. 最后删 papers trigger
```

## 5. 当前决定

```text
不删 papers/sections/paragraphs/sentences trigger
继续保留 outbox
```

## 6. 备注

`import_jats` 同时承担：

```text
运行时 Europe PMC 导入
离线 XML 批量导入
```

改造时必须区分这两条调用链，不能只当 build 工具处理。
