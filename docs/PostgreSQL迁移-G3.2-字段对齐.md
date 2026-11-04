# G3.2a PG Writer 字段对齐

> 日期：2026-11-05  
> 目标：确认 PG-only ingest 不丢 SQLite 写入字段

---

## 1. 已覆盖

| 对象 | 字段 |
|---|---|
| papers | 全部元数据列 |
| paragraphs | text / sequence / page / bbox / section / search_vector |
| sentences | text / sequence / page / bbox / section / char offsets / search_vector |
| figures | caption / path / page / bbox |
| tables | caption / markdown / page |
| citations | raw_text / doi / title / authors / journal / year |
| citation_mentions | ref / page / bbox / context |
| parse_provenance | engines / decision / metrics |
| supplementary_files | filename / type / path / size / description |

新增：

```text
keywords
volume
issue
pages
paper_type
publisher
language
affiliations
funding
parse_status
parse_engine
total_paragraphs
total_figures
total_tables
total_citations
```

## 2. 仍缺失

| 对象 | 状态 | 说明 |
|---|---|---|
| sections | ❌ | 由 build_sections_tree 后置生成 |
| sentence_links | ❌ | 后置生成 |
| paper_links | ❌ | 后置生成 |
| workspace_id | ❌ | 由 tenancy 写路径处理 |
| PDF 原文 | — | 文件系统 |

## 3. 结论

```text
PG-only 可以覆盖 parsed_result 的直接产物
但 sections / links 需要后置阶段也写 PG
```

因此 G3.2 不能只改 `DatabaseWriter.insert_paper`。

还需要：

```text
G3.2b sections -> PG
G3.2c sentence_links / paper_links -> PG
G3.2d PG-only 冒烟
```

## 4. 测试

```text
tests.test_paper_pg_writes 3 OK
tests.test_db_writer_pg_only 2 OK
```

## 5. 当前生产

```text
SCIPAL_INGEST_PG_ONLY=0
SQLite/outbox 仍是主路径
```

## 6. 下一步

```text
G3.2b sections PG-only
```
