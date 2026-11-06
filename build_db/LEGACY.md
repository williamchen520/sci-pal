# build_db Legacy 标注

> 日期：2026-11-06  
> 适用范围：`build_db/`、`scripts/build_*`、离线重建工具

---

## 1. 结论

```text
生产运行时 / cron 不再使用 SQLite 构建路径
以下脚本仅作为离线重建 / 历史兼容工具
```

任何新构建必须优先写 PostgreSQL。

---

## 2. 分类

### A. SQLite legacy（离线）

| 脚本 | 作用 | 状态 |
|---|---|---|
| `build_db/build_xml_db.py` | XML -> SQLite | legacy |
| `build_db/build_database.py` | 主库重建 | legacy |
| `build_db/build_fts.py` | SQLite FTS5 | legacy |
| `build_db/build_xml_fts.py` | XML FTS | legacy |
| `build_db/build_unified_index.py` | 统一索引 | legacy |
| `build_db/build_chunks.py` | chunk 索引 | legacy |
| `build_db/build_summaries.py` | 摘要 | legacy |
| `build_db/build_llm_summaries.py` | LLM 摘要 | legacy |
| `build_db/build_communities.py` | 社区 | legacy |
| `build_db/build_citation_index.py` | 引用索引 | legacy |
| `build_db/build_figure_links.py` | 图表链接 | legacy |
| `build_db/build_paper_graph.py` | 论文图 | legacy |
| `build_db/rebuild_sentence_links.py` | 句子链接 | legacy |
| `build_db/sync_paper_links.py` | 链接同步 | legacy |
| `build_db/structure_v3.py` | 结构 v3 | legacy |
| `build_db/dedup_papers.py` | 去重 | legacy |
| `build_db/backfill_metadata.py` | 元数据回填 | legacy |
| `scripts/build_*` | 各种离线重建 | legacy |

### B. 双路径（可用 PG）

| 脚本 | 说明 |
|---|---|
| `build_db/db_writer.py` | `SCIPAL_INGEST_PG_ONLY=1` 时只写 PG |
| `build_db/parse_service.py` | 通过 DatabaseWriter，PG-only 可用 |
| `build_db/build_sections_tree.py` | PG-only 模式可读 PG |
| `build_db/import_jats.py` | 仍含 SQLite 路径，待迁移 |

### C. PG / v2

| 脚本 | 说明 |
|---|---|
| `build_db/pg_v2_import_xml.py` | scipal_v2 schema，不是生产 |
| `build_db/pg_v2_import_pdf.py` | scipal_v2 schema |
| `build_db/pg_v2_import_missing.py` | v2 补齐 |
| `build_db/generate_postgres_schema.py` | PG schema 生成 |

---

## 3. 使用规则

```text
1. 不在 app 容器 / cron 中运行 legacy 脚本
2. 不在 SCIPAL_SQLITE_QUERY_ONLY=1 的进程里运行
3. 新构建优先 DatabaseWriter(PG_ONLY)
4. 必须写 SQLite 时，显式在维护窗口执行
```

---

## 4. 后续迁移优先级

```text
P1 import_jats.py        JATS 生产 PG 导入
P1 build_sections_tree   PG-only 默认
P2 build_fts / build_xml_fts   ParadeDB 替代
P2 build_unified_index   PG 索引
P3 其余 build_*          归档或重写
```

---

## 5. 当前生产

```text
app / watch-cron / health-cron / backup-cron
均不调用 legacy build 脚本
```
