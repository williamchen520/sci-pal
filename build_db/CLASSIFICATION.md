# build_db 脚本分类

> 日期：2026-11-06  
> 范围：`build_db/*.py`，共 71 个文件  
> 目的：区分 PG 核心、双路径、SQLite legacy、Chroma、离线工具

---

## 1. PG 核心 / 保留

| 脚本 | 说明 |
|---|---|
| `build_fts_pg.py` | GIN 索引维护 |
| `build_xml_db_pg.py` | XML 目录 PG 导入 |
| `build_database_pg.py` | PDF 目录 PG 解析导入 |
| `build_sentences_pg.py` | 句子 PG 重建 |
| `build_unified_index_pg.py` | unified_papers 视图 |
| `import_jats_pg.py` | JATS 直接写 PG |
| `generate_postgres_schema.py` | PG schema 生成 |
| `pg_v2_import_xml.py` | scipal_v2 XML 导入 |
| `pg_v2_import_pdf.py` | scipal_v2 PDF 导入 |
| `pg_v2_import_missing.py` | v2 补齐 |
| `jats_parser.py` | 纯解析 |
| `sentence_geometry.py` | 句子切分 |

---

## 2. 双路径 / 可 PG

| 脚本 | 说明 |
|---|---|
| `db_writer.py` | `SCIPAL_INGEST_PG_ONLY=1` 只写 PG |
| `parse_service.py` | 走 DatabaseWriter，PG-only 可用 |
| `build_sections_tree.py` | PG-only 读 PG（冒烟通过） |
| `build_sentences.py` | PG_ONLY -> `build_sentences_pg.py` |
| `import_jats.py` | PG_ONLY 转 `import_jats_pg` |

---

## 3. SQLite legacy（离线）

| 脚本 | 作用 |
|---|---|
| `build_xml_db.py` | XML -> SQLite，PG 替代 `build_xml_db_pg.py` |
| `build_database.py` | 主库重建，PG 替代 `build_database_pg.py` |
| `build_abstracts_db.py` | DEPRECATED; abstracts 已迁 PG |
| `build_citation_index.py` | 引用索引 |
| `build_communities.py` | 社区 |
| `build_external_edges.py` | 外部边 |
| `build_figure_links.py` | 图表链接 |
| `build_llm_summaries.py` | LLM 摘要 |
| `build_paper_graph.py` | 论文图 |
| `build_sentence_links.py` | 句子链接 |
| `build_summaries.py` | 摘要 |
| `build_xml_fts.py` | XML FTS |
| `build_xml_indexes.py` | XML 索引 |
| `build_unified_index.py` | 联合索引 |
| `backfill_grobid_mentions.py` | GROBID mentions |
| `backfill_jats_figure_links.py` | JATS 图表链接 |
| `backfill_metadata.py` | 元数据回填 |
| `backfill_xml_figures.py` | XML 图 |
| `dedup_papers.py` | 去重 |
| `extract_captions.py` | caption 提取 |
| `fix_figure_numbers.py` | 图号修复 |
| `fix_missing_dois.py` | DOI 补齐 |
| `match_captions_to_figures.py` | caption 匹配 |
| `rebuild_sentence_links.py` | 句子链接重建 |
| `resolve_ref_dois.py` | 引文 DOI |
| `structure_v2.py` | 结构 v2 |
| `structure_v3.py` | 结构 v3 |
| `sync_paper_links.py` | 链接同步 |

---

## 4. SQLite schema legacy

| 脚本 | 说明 |
|---|---|
| `citation_intent_schema.py` | 引文意图表 |
| `claim_pilot_schema.py` | claim 试点表 |
| `claims_schema.py` | claims 表 |
| `review_schema.py` | review 表 |
| `trust_schema.py` | trust 表 |
| `watch_schema.py` | watch 表 |

这些 schema 已由 PG DDL 替代；启动期不再调用。

---

## 5. Chroma / 向量构建

| 脚本 | 说明 |
|---|---|
| `build_embeddings.py` | 段落 embedding |
| `build_contextual_paragraph_index.py` | contextual 集合 |
| `build_summary_vector_index.py` | summary 集合 |
| `build_chunks.py` | chunk 集合 |
| `build_paper_graph.py` | 图 + 向量 |
| `dedup_papers.py` | 去重 + 向量清理 |

G4 未决前仍可能使用；PG 替代是 pgvector + `paragraph_embeddings`。

---

## 6. 离线工具 / 审计

| 脚本 | 作用 |
|---|---|
| `analyze_quality.py` | 质量分析 |
| `audit_structure.py` | 结构审计 |
| `batch_download_from_snapshot.py` | 批量下载 |
| `batch_parse_all.py` | 批量解析 |
| `build_claims.py` | claims 构建 |
| `build_domain_profiles.py` | 领域画像 |
| `build_paper.py` | 单篇构建 |
| `check_pdf_bookmarks.py` | 书签检查 |
| `check_retractions.py` | 撤稿检查 |
| `download_test_papers.py` | 测试下载 |
| `explore_docling_structure.py` | 结构探查 |
| `fix_sections_from_bookmarks.py` | 章节修复 |
| `seed_test_data.py` | 测试数据 |
| `validate_section_tree.py` | 章节校验 |
| `verify_database.py` | 数据库校验 |
| `mention_patterns.py` | 提及模式 |
| `test_docling.py` | 手动测试 |
| `test_hierarchical_pdf.py` | 手动测试 |
| `test_image_export.py` | 手动测试 |
| `test_intext_citations.py` | 手动测试 |

---

## 7. 规则

```text
1. 生产 app/cron 只调用 PG 核心或双路径 PG 分支
2. legacy 脚本只在维护窗口离线运行
3. 新构建不得新增 SQLite 写路径
4. 任何新 build_* 必须有 PG 对应
```

---

## 8. 当前结论

```text
PG 核心       9
双路径        5
SQLite legacy 28
schema legacy 6
Chroma        6
离线工具      20
```

其中 3 个脚本跨类：

```text
build_paper_graph
dedup_papers
build_paper
```

唯一文件数仍为 71。
