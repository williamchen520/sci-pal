# SciPal 静态架构骨架 — RAW 采集

> **工单**：阶段一 · 静态架构骨架扫描（只读）
> **性质**：事实层原始记录。**本文不含任何架构判断、改造建议或优先级评估。**
> **生成方式**：`codebase-memory-mcp` v0.12.1 → `index_repository` + `get_architecture(aspects=["all"])` + 补充只读 Cypher/源码检索。

---

## 0. 采集元信息

| 项 | 值 |
|---|---|
| 仓库 | `D:\sciPal` |
| 分支 | `dev`（`git status -sb` → `## dev...origin/dev`，与远端同步） |
| HEAD | `68c5a5c` V33.17: 从 master 合入 dev 缺失的资产 |
| VERSION 文件 | `V33.17` |
| 采集时间 | 2026-10-24 |
| MCP 服务 | `codebase-memory-mcp` v0.12.1 |
| 项目标识 | `D-sciPal` |
| 写入范围 | **仅本文件**（`docs/架构骨架-raw.md`），其余文件零改动 |

### 0.1 MCP 调用记录（实际入参）

**调用 1 — 索引**

```json
{
  "tool": "index_repository",
  "arguments": { "repo_path": "d:/sciPal", "mode": "full", "async": false }
}
```

**调用 2 — 架构视图**

```json
{
  "tool": "get_architecture",
  "arguments": { "project": "D-sciPal", "aspects": ["all"], "format": "tree" }
}
```

**补充只读查询（Cypher，全部只读）**

```cypher
-- 路由节点属性探测
MATCH (r:Route) RETURN properties(r) AS props LIMIT 3
-- HTTP 跨服务/外部调用
MATCH (a)-[r:HTTP_CALLS]->(b) RETURN a.name, labels(a), b.name, properties(r) LIMIT 60
-- 文件级 IMPORTS
MATCH (a)-[r:IMPORTS]->(b) RETURN labels(a), a.name, labels(b), b.name LIMIT 60
-- 全局 CALLS 文件对
MATCH (a:Function)-[:CALLS]->(b:Function) RETURN a.file_path, b.file_path, count(*) ORDER BY count(*) DESC LIMIT 40
-- api_server.py 出向调用链
MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.file_path = 'api_server.py'
  RETURN a.name, b.name, b.file_path ORDER BY a.name, b.name LIMIT 250
```

---

## 1. 索引结果与锚点核对

### 1.1 索引规模

| 指标 | 值 |
|---|---|
| 节点数 | **3,922** |
| 边数 | **12,818** |
| 索引文件（File 节点） | **230** |
| 代码文件合计 | **189** |
| 识别语言数 | **5** |
| skipped | 0 |
| parse_unusable | 0 |
| parse_partial | 5（HTML，行号见 1.4） |

### 1.2 语言分布（`get_architecture` languages）

| 语言 | 文件数 |
|---|---|
| Python | **157** |
| HTML | 15 |
| JavaScript | 9 |
| Bash | 7 |
| CSS | 1 |

### 1.3 自检锚点核对

| 锚点 | 期望 | 实测 | 结论 |
|---|---|---|---|
| `.py` 文件数 | 157 | **157**（索引 Python 文件数；磁盘实测同值） | ✅ 一致 |
| `services/` 子域 | 12 | **12** | ✅ 一致 |

`services/` 12 个子域（目录实测）：
`ai`、`data`、`embeddings`(占位 `__init__.py`)、`l3`、`pdf`、`qa`、`query`、`review`、`search`、`user`、`utils`、`writing`

**差异说明（1 项，不影响锚点）**：
- 磁盘 `.py` 共 157 个，其中 `_test_v3317b.py` 为**未跟踪文件**（`git ls-files "*.py"` 为 156 个）。锚点 157 与磁盘一致；纳入版本控制的 Python 文件为 156 个。

### 1.4 覆盖缺口清单（工具原始输出）

**排除目录（by design，25 个，含 `data`）**

```json
{
  "excluded": {
    "dirs": [".codebuddy", ".git", ".vscode", "abstracts_xml", "data"],
    "count": 25,
    "truncated": true
  },
  "not_indexed_files_count": 465
}
```

未索引文件示例（原因均为 `gitignore`）：`2nd-科研写作-Science research writing for non-native speakers of English.pdf`、`AIM-22-210.pdf`、`blt-11-217.pdf`、`Bookshelf_NBK988.pdf`、`JCI0734288.pdf` …（共 465 个）。

**部分解析（parse_partial = 5，均为文档 HTML 内嵌脚本）**

| 文件 | 可能缺失行号 |
|---|---|
| `docs/sci-pal-architecture-v2.html` | 203, 422 |
| `docs/sci-pal-full-dataflow-with-parsers.html` | 102, 145 |
| `docs/sci-pal-incremental-update-subgraph.html` | 375, 473 |
| `docs/sci-pal-pdf-parsers-architecture.html` | 116, 140-141, 242, 341 |
| `docs/sci-pal-three-layer-architecture.html` | 219 |

---

## 2. `get_architecture(aspects=["all"])` 原始输出

```text
project: D-sciPal
total_nodes: 3922
total_edges: 12818
node_labels: 17  (cols: label count)
  Section 1311
  Variable 644
  Method 586
  Function 552
  File 230
  Module 207
  Class 134
  DiagramElement 85
  Route 82
  Folder 30
  EnvVar 27
  Package 19
  Diagram 7
  Decorator 5
  Branch 1
  Process 1
  Project 1
edge_types: 27  (cols: type count)
  DEFINES 5277
  CALLS 2869
  USAGE 1367
  WRITES 1022
  DEFINES_METHOD 581
  MENTIONS 390
  REFERENCES_FILE 286
  CONTAINS_FILE 230
  IMPORTS 128
  DECORATES 126
  DIAGRAM_ARROW 81
  SIMILAR_TO 75
  HANDLES 67
  SEMANTICALLY_RELATED 64
  HTTP_CALLS 53
  CONFIGURES 47
  DEPENDS_ON 38
  DATA_FLOWS 36
  CONTAINS_FOLDER 29
  INHERITS 20
  FILE_CHANGES_WITH 9
  TESTS 9
  CALL_REFERENCE 5
  OVERRIDE 4
  RAISES 3
  HAS_BRANCH 1
  SPAWNS 1
languages: 5  (cols: language files)
  Python 157
  HTML 15
  JavaScript 9
  Bash 7
  CSS 1
packages: 15  (cols: name nodes fan_in fan_out)
  Flask 1 0 0
  PyMuPDF 1 0 0
  PyYAML 1 0 0
  Werkzeug 1 0 0
  chromadb 1 0 0
  docling 1 0 0
  docling-core 1 0 0
  flask-cors 1 0 0
  networkx 1 0 0
  pdfplumber 1 0 0
  pyarrow 1 0 0
  pydantic 1 0 0
  pypdf 1 0 0
  python-dotenv 1 0 0
  requests 1 0 0
entry_points: 20  (cols: qn file)
  D-sciPal.batch_download_pmc.main batch_download_pmc.py
  D-sciPal.build_abstracts_db.main build_abstracts_db.py
  D-sciPal.build_db.batch_download_from_snapshot.main build_db/batch_download_from_snapshot.py
  D-sciPal.build_db.build_abstracts_db.main build_db/build_abstracts_db.py
  D-sciPal.build_db.build_chunks.main build_db/build_chunks.py
  D-sciPal.build_db.build_communities.main build_db/build_communities.py
  D-sciPal.build_db.build_figure_links.main build_db/build_figure_links.py
  D-sciPal.build_db.build_paper_graph.main build_db/build_paper_graph.py
  D-sciPal.build_db.build_sentence_links.main build_db/build_sentence_links.py
  D-sciPal.build_db.build_sentences.main build_db/build_sentences.py
  D-sciPal.build_db.build_unified_index.main build_db/build_unified_index.py
  D-sciPal.build_db.build_xml_db.main build_db/build_xml_db.py
  D-sciPal.build_db.build_xml_fts.main build_db/build_xml_fts.py
  D-sciPal.build_db.build_xml_indexes.main build_db/build_xml_indexes.py
  D-sciPal.build_db.dedup_papers.main build_db/dedup_papers.py
  D-sciPal.build_db.fix_missing_dois.main build_db/fix_missing_dois.py
  D-sciPal.build_db.fix_sections_from_bookmarks.main build_db/fix_sections_from_bookmarks.py
  D-sciPal.build_db.resolve_ref_dois.main build_db/resolve_ref_dois.py
  D-sciPal.download_bioinformatics_methods.main download_bioinformatics_methods.py
  D-sciPal.download_openalex.main download_openalex.py
routes: 20  (cols: method path handler)
  ANY / -
  ANY /<path:path> -
  ANY /upload -
  ANY /abstracts/<paper_id> -
  ANY /<paper_id>/fulltext -
  ANY /text -
  ANY /figure -
  ANY /citation -
  ANY /paper -
  ANY /unified -
  ANY /ask -
  ANY /status -
  ANY /api/health -
  ANY /api/tasks -
  ANY /api/tasks/<task_id> -
  ANY /api/tasks/<task_id>/events -
  ANY /api/retrieve -
  - /api/qa/ask -
  - /api/qa/status -
  ANY /api/agentic/search -
hotspots: 10  (cols: qn fan_in)
  builtins.len 333
  builtins.print 314
  builtins.list.append 216
  builtins.dict.get 49
  builtins.str.lower 44
  D-sciPal.frontend.src.outline_editor.showMessage 17
  D-sciPal.self_check.print_header 12
  D-sciPal.scripts.self_check.check 12
  D-sciPal.self_check.check_pass 11
  D-sciPal.self_check.check_fail 9
boundaries: 10  (cols: from to calls)
  review list 79
  search len 68
  search list 63
  review len 61
  search print 37
  review print 32
  search str 28
  review dict 27
  review str 26
  parsers print 14
layers: 38  (cols: name layer reason)
  - api "has HTTP route definitions"
  batch_download_from_snapshot internal "fan-in=0, fan-out=0"
  batch_download_pmc internal "fan-in=0, fan-out=0"
  build_abstracts_db internal "fan-in=0, fan-out=0"
  build_chunks internal "fan-in=0, fan-out=0"
  build_communities internal "fan-in=0, fan-out=0"
  build_figure_links internal "fan-in=0, fan-out=0"
  build_paper_graph internal "fan-in=0, fan-out=0"
  build_sentence_links internal "fan-in=0, fan-out=0"
  build_sentences internal "fan-in=0, fan-out=0"
  build_unified_index internal "fan-in=0, fan-out=0"
  build_xml_db internal "fan-in=0, fan-out=0"
  build_xml_fts internal "fan-in=0, fan-out=0"
  build_xml_indexes internal "fan-in=0, fan-out=0"
  dedup_papers internal "fan-in=0, fan-out=0"
  dict core "high fan-in (27 in, 0 out)"
  download_all internal "fan-in=0, fan-out=0"
  download_all_xml internal "fan-in=0, fan-out=0"
  download_bioinformatics_methods internal "fan-in=0, fan-out=0"
  download_openalex internal "fan-in=0, fan-out=0"
  download_pmc internal "fan-in=0, fan-out=0"
  download_pmc_v2 internal "fan-in=0, fan-out=0"
  download_pmc_xml internal "fan-in=0, fan-out=0"
  download_protocols internal "fan-in=0, fan-out=0"
  download_pubmed_abstracts internal "fan-in=0, fan-out=0"
  download_test_papers internal "fan-in=0, fan-out=0"
  fix_missing_dois internal "fan-in=0, fan-out=0"
  fix_sections_from_bookmarks internal "fan-in=0, fan-out=0"
  len core "high fan-in (129 in, 0 out)"
  list core "high fan-in (142 in, 0 out)"
  parse_pmc_xml internal "fan-in=0, fan-out=0"
  parsers entry "only outbound calls"
  print core "high fan-in (83 in, 0 out)"
  resolve_ref_dois internal "fan-in=0, fan-out=0"
  review entry "only outbound calls"
  search entry "only outbound calls"
  self_check internal "fan-in=0, fan-out=0"
  str core "high fan-in (54 in, 0 out)"
clusters: 12  (cols: id label members cohesion top_nodes packages edge_types)
  6 services 145 0.4943 str;int;dict;ask;parse services;str;int;dict;routes CALLS
  0 build_db 136 0.425 print;check;main;main;main services;print;build_db;download_bioinformatics_methods;scripts CALLS
  9 services 119 0.3907 append;chat_json;import_zotero_metadata;assess_impact;format_citation_list list;services;build_db;import_zotero_metadata;check_parse_status CALLS
  1 services 117 0.3902 len;range;retrieve;build_database;search services;len;range;list;build_db CALLS
  5 services 67 0.4062 get;list;_generate_with_llm;main;optimize_for_journal services;list;str;dict;build_db CALLS
  8 services 62 0.4569 lower;generate;chat;_write_draft;_extract_batch str;services;build_db CALLS
  12 build_db 36 0.4719 DatabaseWriter;insert_paper;parse_paper;batch_parse_new;parse routes;build_db;batch_parse_new_papers;app;database CALLS
  14 services 35 0.6557 check_v25_19_retrieval_optimization;__init__;search;__init__;_request services;scripts;api_server CALLS
  56 self_check 28 0.8043 check_v334_features;print_header;main;check_pass;check_fail services;self_check CALLS
  3 services 28 0.4359 _run_download;search;download_batch;main;_save_to_disk services;import_xml;download_pmc_xml;scripts;api_server CALLS
  33 frontend 26 1 showMessage;refreshPaperList;init;initModules;loadLocalPapers frontend CALLS
  92 frontend 24 1 showToast;pollDownloadStatus;esc;openHistoryModal;retryTaskFailed frontend CALLS
file_tree: 260  (cols: path type children)
  .env.example file 0
  AGENTS.md file 0
  AI_CONTEXT.md file 0
  ARCHITECTURE.json file 0
  ARCHITECTURE.md file 0
  CHANGES_V18.0.md file 0
  CHANGES_V18.2.md file 0
  CODEBUDDY.md file 0
  IMPROVEMENT_PLAN.md file 0
  README-WINDOWS.md file 0
  README.md file 0
  WINDOWS-INSTALL-GUIDE.md file 0
  WORKLOG.md file 0
  WORK_LOG.md file 0
  _test_v3317b.py file 0
  api_server.py file 0
  app.py file 0
  backfill_paper_metadata.py file 0
  batch_download_pmc.py file 0
  batch_parse_new_papers.py file 0
  build_abstracts_db.py file 0
  build_db dir 38
  build_db/INSTALL.md file 0
  build_db/__init__.py file 0
  build_db/analyze_quality.py file 0
  build_db/batch_download_from_snapshot.py file 0
  build_db/batch_parse_all.py file 0
  build_db/build_abstracts_db.py file 0
  build_db/build_chunks.py file 0
  build_db/build_citation_index.py file 0
  build_db/build_communities.py file 0
  build_db/build_database.py file 0
  build_db/build_embeddings.py file 0
  build_db/build_figure_links.py file 0
  build_db/build_fts.py file 0
  build_db/build_paper.py file 0
  build_db/build_paper_graph.py file 0
  build_db/build_sentence_links.py file 0
  build_db/build_sentences.py file 0
  build_db/build_unified_index.py file 0
  build_db/build_xml_db.py file 0
  build_db/build_xml_fts.py file 0
  build_db/build_xml_indexes.py file 0
  build_db/check_pdf_bookmarks.py file 0
  build_db/db_writer.py file 0
  build_db/dedup_papers.py file 0
  build_db/download_test_papers.py file 0
  build_db/explore_docling_structure.py file 0
  build_db/extract_captions.py file 0
  build_db/fix_missing_dois.py file 0
  build_db/fix_sections_from_bookmarks.py file 0
  build_db/match_captions_to_figures.py file 0
  build_db/parsers dir 8
  build_db/parsers/__init__.py file 0
  build_db/parsers/base_parser.py file 0
  build_db/parsers/docling_parser.py file 0
  build_db/parsers/grobid_parser.py file 0
  build_db/parsers/journal_optimizer.py file 0
  build_db/parsers/mineru_parser.py file 0
  build_db/parsers/parser_orchestrator.py file 0
  build_db/parsers/pdfplumber_parser.py file 0
  build_db/resolve_ref_dois.py file 0
  build_db/seed_test_data.py file 0
  build_db/test_docling.py file 0
  build_db/test_hierarchical_pdf.py file 0
  build_db/test_image_export.py file 0
  build_db/test_intext_citations.py file 0
  build_db/verify_database.py file 0
  build_paragraph_vector_index.py file 0
  build_vector_index.py file 0
  check_parse_status.py file 0
  config dir 2
  config/__init__.py file 0
  config/settings.py file 0
  create_supplementary_table.py file 0
  database dir 2
  database/__init__.py file 0
  database/init_db.py file 0
  deploy_v25.11.sh file 0
  deploy_v25.12.sh file 0
  deploy_v25.13.sh file 0
  deploy_v25.14.sh file 0
  diagnose_abstract_sections.py file 0
  docs dir 27
  docs/ARCHITECTURE.md file 0
  docs/DATA_LAYER_ARCHITECTURE_V2.html file 0
  docs/DATA_LAYER_ARCHITECTURE_V2.md file 0
  "docs/P2 优先级分类+6幅架构图索引+明天工作计划）.md" file 0
  docs/README-WINDOWS.md file 0
  docs/README.md file 0
  docs/WINDOWS-INSTALL-GUIDE.md file 0
  docs/WORKLOG.md file 0
  docs/requirements.txt file 0
  "docs/sci-pal 核心数据流图.pdf" file 0
  "docs/sci-pal 系统完整架构图.pdf" file 0
  docs/sci-pal-architecture-v2.html file 0
  docs/sci-pal-architecture.html file 0
  docs/sci-pal-dataflow-v2.html file 0
  docs/sci-pal-dataflow.html file 0
  docs/sci-pal-full-dataflow-with-parsers.html file 0
  docs/sci-pal-incremental-update-subgraph.html file 0
  docs/sci-pal-pdf-parsers-architecture.html file 0
  docs/sci-pal-three-layer-architecture.html file 0
  docs/任务.md file 0
  docs/协作约定.md file 0
  docs/变更日志.md file 0
  docs/工作日志 dir 1
  docs/工作日志/2026-10.md file 0
  docs/接口.md file 0
  docs/接口明细.md file 0
  docs/架构.md file 0
  docs/架构总览.md file 0
  documents dir 1
  documents/pmc_metadata.json file 0
  download_bioinformatics_methods.py file 0
  download_openalex.py file 0
  download_pmc_v2.py file 0
  download_pmc_xml.py file 0
  download_protocols.py file 0
  download_pubmed_abstracts.py file 0
  fetch_from_ncbi.py file 0
  fetch_metadata.py file 0
  frontend dir 7
  frontend/compare.html file 0
  frontend/index.html file 0
  frontend/qa.html file 0
  frontend/review.html file 0
  frontend/src dir 10
  frontend/src/outline_core.js file 0
  frontend/src/outline_editor.js file 0
  frontend/src/paper_importer.js file 0
  frontend/src/paper_list.js file 0
  frontend/src/pdf_annotator.js file 0
  frontend/src/pdf_viewer.js file 0
  frontend/src/resizer.js file 0
  frontend/src/review.css file 0
  frontend/src/review.js file 0
  frontend/src/supplementary_manager.js file 0
  frontend/tasks.html file 0
  frontend/viewer.html file 0
  import_xml.py file 0
  import_xml_v2.py file 0
  import_zotero_metadata.py file 0
  indexes dir 1
  indexes/__init__.py file 0
  migrate_papers_table_v25.18.py file 0
  plugins dir 1
  plugins/academic_research_skills dir 5
  plugins/academic_research_skills/README.md file 0
  plugins/academic_research_skills/__init__.py file 0
  plugins/academic_research_skills/config.py file 0
  plugins/academic_research_skills/core.py file 0
  plugins/academic_research_skills/test_plugin.py file 0
  prompts dir 4
  prompts/abstract_writing_template.md file 0
  prompts/academic_writing_style.md file 0
  prompts/imrad_paper_structure.md file 0
  prompts/literature_review_template.md file 0
  requirements.txt file 0
  routes dir 5
  routes/__init__.py file 0
  routes/ai_routes.py file 0
  routes/paper_routes.py file 0
  routes/search_routes.py file 0
  routes/writing_routes.py file 0
  scripts dir 10
  scripts/build_xml_db.py file 0
  scripts/download_100_topics.sh file 0
  scripts/download_all.py file 0
  scripts/download_all_xml.py file 0
  scripts/download_pmc.py file 0
  scripts/download_pmc_xml.py file 0
  scripts/parse_pmc_xml.py file 0
  scripts/run_tests.sh file 0
  scripts/self_check.py file 0
  scripts/tune_retrieval.py file 0
  self_check.py file 0
  services dir 13
  services/__init__.py file 0
  services/ai dir 4
  services/ai/__init__.py file 0
  services/ai/ai_service.py file 0
  services/ai/envelope_builder.py file 0
  services/ai/rag_validator.py file 0
  services/data dir 2
  services/data/__init__.py file 0
  services/data/version_manager.py file 0
  services/l3 dir 1
  services/l3/__init__.py file 0
  services/pdf dir 2
  services/pdf/__init__.py file 0
  services/pdf/annotator.py file 0
  services/qa dir 2
  services/qa/__init__.py file 0
  services/qa/qa_service.py file 0
  services/query dir 2
  services/query/__init__.py file 0
  services/query/search_service.py file 0
  services/review dir 18
  services/review/__init__.py file 0
  services/review/citation_formatter.py file 0
  services/review/citation_verifier.py file 0
  services/review/conflict_detector.py file 0
  services/review/evidence_card_incremental_manager.py file 0
  services/review/evidence_extractor.py file 0
  services/review/export_manager.py file 0
  services/review/impact_analyzer.py file 0
  services/review/llm_client.py file 0
  services/review/models.py file 0
  services/review/outline_generator.py file 0
  services/review/outline_store.py file 0
  services/review/relation_extractor.py file 0
  services/review/review_generator.py file 0
  services/review/review_store.py file 0
  services/review/sentence_locator.py file 0
  services/review/task_manager.py file 0
  services/review/user_feedback.py file 0
  services/search dir 24
  services/search/abbreviation_expander.py file 0
  services/search/abstract_search.py file 0
  services/search/agentic_search.py file 0
  services/search/boilerplate_filter.py file 0
  services/search/chunker.py file 0
  services/search/context_expander.py file 0
  services/search/fts_query_builder.py file 0
  services/search/graph_traverser.py file 0
  services/search/hybrid_retriever.py file 0
  services/search/hybrid_search.py file 0
  services/search/hybrid_search_v2.py file 0
  services/search/mmr_diversifier.py file 0
  services/search/online_downloader.py file 0
  services/search/online_search.py file 0
  services/search/protocols_io_client.py file 0
  services/search/query_expander.py file 0
  services/search/query_router.py file 0
  services/search/reference_filter.py file 0
  services/search/reranker.py file 0
  services/search/retrieval_diagnostics.py file 0
  services/search/retrieval_observability.py file 0
  services/search/sentence_relation_classifier.py file 0
  services/search/unified_retriever.py file 0
  services/search/unified_search.py file 0
  services/unified_task_manager.py file 0
  services/user dir 1
  services/user/__init__.py file 0
  services/utils dir 3
  services/utils/__init__.py file 0
  services/utils/retry_utils.py file 0
  services/utils/structured_logger.py file 0
  services/writing dir 2
  services/writing/__init__.py file 0
  services/writing/writing_service.py file 0
  test_workflow.sh file 0
  tests dir 1
  tests/__init__.py file 0
  utils dir 1
  utils/__init__.py file 0
  validators dir 1
  validators/__init__.py file 0
  生物信息学方法数据库调研与建库指南.md file 0
```

---

## 3. 补充采集（补 `get_architecture` 输出缺项）

> 说明：`get_architecture(all)` 的 `routes` 段 `handler` 列全为空、`Route` 节点仅含 `method` 属性（无 `path`）；`entry_points` 未包含 `api_server.py` / `app.py`。以下为补齐所需的**源码与图事实**，均为只读采集。

### 3.1 进程入口点（源码事实）

| 入口 | 位置 | 事实 |
|---|---|---|
| 主服务 | `api_server.py:2031` | `if __name__ == "__main__":` → 读取 `SCIPAL_HOST` 等环境变量 → `api_server.py:2054` `app.run(host=host, port=port, debug=debug, threaded=False)` |
| 旧版工厂 | `app.py:9` | `def create_app()`，`Flask(__name__, static_folder='frontend', static_url_path='')` |
| 旧版入口 | `app.py:48-50` | `if __name__ == "__main__": app = create_app(); app.run(host=HOST, port=PORT, debug=DEBUG)` |
| 蓝图注册 | `create_app` | `HTTP_CALLS` 边记录：`app.register_blueprint` → `/api/papers`、`/api/search`、`/api/ai` |

`get_architecture` 识别到的 20 个 `main()` 入口均位于 `build_db/`、`download_*.py`、`batch_download_pmc.py` 等批处理脚本（清单见第 2 节 `entry_points`）。

其余含 `if __name__ == "__main__"` 的模块（源码检索，节选）：`services/search/*.py`（`unified_search`、`unified_retriever`、`retrieval_diagnostics`、`reranker`、`reference_filter`、`query_router`、`query_expander`、`protocols_io_client`、`mmr_diversifier`、`hybrid_search_v2`、`hybrid_search`、`graph_traverser`、`fts_query_builder`、`context_expander`、`chunker`、`boilerplate_filter`、`agentic_search`、`abstract_search`、`abbreviation_expander`）、`database/init_db.py:328`、`build_vector_index.py:88`、`build_paragraph_vector_index.py:103`、`check_parse_status.py:180` 等。

### 3.2 HTTP 路由清单（源码 `@*.route` 全量，共 70 条）

**A. `api_server.py`（51 条，单体 Flask 应用）**

| 行号 | 路由 | methods |
|---|---|---|
| 167 | `/api/health` | GET（默认） |
| 180 | `/api/tasks` | GET |
| 191 | `/api/tasks/<task_id>` | GET |
| 201 | `/api/tasks/<task_id>/events` | GET |
| 211 | `/api/retrieve` | GET, POST |
| 263 | `/api/qa/ask` | POST |
| 294 | `/api/qa/status` | GET |
| 309 | `/api/agentic/search` | GET, POST |
| 349 | `/api/papers` | GET |
| 364 | `/api/papers/<paper_id>` | GET |
| 408 | `/api/papers/<paper_id>/graph` | GET |
| 445 | `/api/graph/stats` | GET |
| 455 | `/api/communities` | GET |
| 527 | `/api/review/outline` | GET, POST |
| 599 | `/api/review/running_task` | GET |
| 612 | `/api/review/task/<task_id>` | GET |
| 628 | `/api/review/cancel/<task_id>` | POST |
| 641 | `/api/review/assign_papers` | POST |
| 676 | `/api/review/search_and_assign` | POST |
| 718 | `/api/review/outline/saved` | GET |
| 729 | `/api/review/outline/saved/<name>` | GET |
| 742 | `/api/review/outline/save` | POST |
| 778 | `/api/review/outline/saved/<name>` | DELETE |
| 791 | `/api/review/generate` | GET, POST |
| 893 | `/api/review/<review_id>` | GET |
| 903 | `/api/review/<review_id>/sentence/<sentence_id>` | GET |
| 913 | `/api/review/llm_status` | GET |
| 937 | `/api/papers/local` | GET |
| 1012 | `/api/search/hybrid` | GET, POST |
| 1069 | `/api/search/online` | GET, POST |
| 1136 | `/api/search/download_online` | POST |
| 1193 | `/api/search/download_status` | GET |
| 1242 | `/api/search/download_history` | GET |
| 1276 | `/api/search/download_queue` | GET |
| 1311 | `/api/search/retry_download` | POST |
| 1381 | `/api/search/clear_download_history` | POST |
| 1404 | `/api/papers/parse` | POST |
| 1500 | `/api/papers/<paper_id>/pdf` | GET |
| 1525 | `/api/abstracts/list` | GET |
| 1582 | `/api/abstracts/<paper_id>` | GET |
| 1621 | `/api/papers/<paper_id>/supplementary` | GET |
| 1630 | `/api/papers/<paper_id>/supplementary` | POST |
| 1704 | `/api/papers/<paper_id>/supplementary/<supp_id>/download` | GET |
| 1723 | `/api/papers/<paper_id>/supplementary/<supp_id>` | DELETE |
| 1756 | `/api/papers/import` | POST |
| 1822 | `/api/papers/<paper_id>/supplementary/link` | POST |
| 1882 | `/api/papers/<paper_id>/annotate` | POST |
| 1921 | `/api/papers/<paper_id>/annotations` | GET |
| 1944 | `/` | GET（默认） |
| 1949 | `/<path:path>` | GET（默认，静态兜底） |

**B. `routes/` 蓝图（17 条）**

| 文件 | 行号 | 路由（含蓝图前缀） | methods |
|---|---|---|---|
| `paper_routes.py` | 10 | `@paper_bp.route("/")` → `/api/papers/` | GET |
| `paper_routes.py` | 31 | `/<paper_id>` → `/api/papers/<paper_id>` | GET |
| `paper_routes.py` | 44 | `/upload` → `/api/papers/upload` | POST |
| `paper_routes.py` | 98 | `/abstracts/<paper_id>` → `/api/papers/abstracts/<paper_id>` | GET |
| `paper_routes.py` | 121 | `/<paper_id>/fulltext` → `/api/papers/<paper_id>/fulltext` | GET |
| `ai_routes.py` | 10 | `/ask` → `/api/ai/ask` | POST |
| `ai_routes.py` | 30 | `/status` → `/api/ai/status` | GET |
| `search_routes.py` | 10 | `/text` → `/api/search/text` | GET |
| `search_routes.py` | 28 | `/figure` → `/api/search/figure` | GET |
| `search_routes.py` | 46 | `/citation` → `/api/search/citation` | GET |
| `search_routes.py` | 64 | `/paper` → `/api/search/paper` | GET |
| `search_routes.py` | 81 | `/unified` → `/api/search/unified` | GET |
| `writing_routes.py` | 13 | `/write_paper` → `/api/writing/write_paper` | POST |
| `writing_routes.py` | 35 | `/write_abstract` → `/api/writing/write_abstract` | POST |
| `writing_routes.py` | 57 | `/write_literature_review` → `/api/writing/write_literature_review` | POST |
| `writing_routes.py` | 78 | `/polish_text` → `/api/writing/polish_text` | POST |
| `writing_routes.py` | 98 | `/status` → `/api/writing/status` | GET |

**C. `app.py`（2 条）**

| 行号 | 路由 | methods |
|---|---|---|
| 34 | `/` | GET（默认） |
| 38 | `/api/health` | GET（默认） |

### 3.3 模块调用链

#### 3.3.1 `api_server.py` 出向调用（Cypher 实测，53 条 CALLS 全量）

```text
caller                          callee                     callee_file
assign_papers_to_outline_route  assign_papers_to_outline   services/review/review_generator.py
assign_papers_to_outline_route  print                      <python-builtins>
clear_download_history          get_task_manager           services/search/online_downloader.py
delete_saved_outline            get_outline_store          api_server.py
delete_supplementary_file       print                      <python-builtins>
download_history                get_task_manager           services/search/online_downloader.py
download_history                len                        <python-builtins>
download_online_papers          get_online_downloader      services/search/online_downloader.py
download_online_papers          len                        <python-builtins>
download_queue_status           get_task_manager           services/search/online_downloader.py
download_status                 get_task_manager           services/search/online_downloader.py
generate_review                 get_llm_client             api_server.py
generate_review                 get_review_generator       api_server.py
generate_review                 get_review_store           api_server.py
generate_review                 print                      <python-builtins>
get_llm_client                  create_llm_client          services/review/llm_client.py
get_review_detail               get_review_store           api_server.py
get_review_generator            get_llm_client             api_server.py
get_review_generator            get_retriever              api_server.py
get_review_sentence             get_review_store           api_server.py
graph_stats                     get_graph                  api_server.py
hybrid_search_api               get_hybrid_retriever       api_server.py
import_paper                    len                        <python-builtins>
import_paper                    print                      <python-builtins>
link_supplementary_file         print                      <python-builtins>
list_communities                len                        <python-builtins>
list_local_papers               len                        <python-builtins>
list_papers                     len                        <python-builtins>
list_saved_outlines             get_outline_store          api_server.py
list_saved_outlines             len                        <python-builtins>
list_unified_tasks              len                        <python-builtins>
load_saved_outline              get_outline_store          api_server.py
online_search_api               get_online_searcher        services/search/online_search.py
online_search_api               len                        <python-builtins>
paper_graph                     get_graph                  api_server.py
paper_graph                     len                        <python-builtins>
parse_local_paper               len                        <python-builtins>
parse_local_paper               print                      <python-builtins>
qa_ask                          get_qa_service             api_server.py
qa_ask                          print                      <python-builtins>
qa_status                       get_qa_service             api_server.py
retrieve                        _parse_filters             api_server.py
retrieve                        get_retriever              api_server.py
retry_download                  get_online_downloader      services/search/online_downloader.py
retry_download                  get_task_manager           services/search/online_downloader.py
retry_download                  len                        <python-builtins>
review_llm_status               get_llm_client             api_server.py
run_db_migrations               print                      <python-builtins>
save_outline                    get_outline_store          api_server.py
search_and_assign_route         get_retriever              api_server.py
search_and_assign_route         print                      <python-builtins>
search_and_assign_route         search_and_assign_papers   services/review/review_generator.py
upload_supplementary_file       print                      <python-builtins>
```

#### 3.3.2 `services/` 内部跨函数调用（Cypher 实测，仅 7 组文件对）

```text
src_file                                 dst_file                                 calls
services/unified_task_manager.py         services/unified_task_manager.py         12
services/review/citation_formatter.py    services/review/citation_formatter.py    10
services/search/reference_filter.py      services/search/reference_filter.py       7
services/search/boilerplate_filter.py    services/search/boilerplate_filter.py     3
services/search/agentic_search.py        services/search/agentic_search.py         2
services/search/protocols_io_client.py   services/search/protocols_io_client.py    2
services/review/review_generator.py      services/review/review_generator.py        1
```

#### 3.3.3 全局 CALLS 文件对 Top 20（含 `<python-builtins>`）

```text
src_file                          dst_file                          calls
self_check.py                     self_check.py                      64
frontend/src/outline_editor.js    frontend/src/outline_editor.js     45
frontend/index.html               frontend/index.html                38
scripts/self_check.py             scripts/self_check.py              28
frontend/src/review.js            frontend/src/review.js             24
api_server.py                     <python-builtins>                  22
scripts/self_check.py             <python-builtins>                  21
frontend/src/outline_core.js      frontend/src/outline_core.js       21
api_server.py                     api_server.py                      20
fetch_metadata.py                 fetch_metadata.py                  15
build_db/build_abstracts_db.py    <python-builtins>                  12
build_db/build_database.py        build_db/build_database.py         12
services/unified_task_manager.py  services/unified_task_manager.py   12
build_abstracts_db.py             <python-builtins>                  11
services/review/citation_formatter.py  services/review/citation_formatter.py  10
self_check.py                     <python-builtins>                  10
frontend/src/paper_importer.js    frontend/src/paper_importer.js      9
build_db/download_test_papers.py  <python-builtins>                   8
build_db/build_database.py        <python-builtins>                   8
frontend/src/pdf_annotator.js     frontend/src/pdf_annotator.js       8
```

跨文件调用样本（非 builtins）：`api_server.py → services/search/online_downloader.py`（7 次）、`api_server.py → services/review/review_generator.py`、`api_server.py → services/search/online_search.py`、`api_server.py → services/review/llm_client.py`（见 3.3.1）。

#### 3.3.4 模块导入关系（`IMPORTS` 边，128 条，节选）

```text
a(File)                  a.name                         b(类型)   b.name
api_server.py            api_server.py                  Module    services/review/task_manager.py
app.py                   app.py                         Module    config/settings.py
build_paper.py           build_paper.py                 Class     ParserOrchestrator
build_paper.py           build_paper.py                 Class     DatabaseWriter
db_writer.py             db_writer.py                   Module    config/settings.py
mineru_parser.py         mineru_parser.py               Class     BaseParser
parser_orchestrator.py   parser_orchestrator.py         Class     DoclingParser
pdfplumber_parser.py     pdfplumber_parser.py           Class     BaseParser
init_db.py               init_db.py                     Module    config/settings.py
ai_routes.py             ai_routes.py                   Class     AIService
search_routes.py         search_routes.py               Class     SearchService
writing_routes.py        writing_routes.py              Class     WritingService
ai_service.py            ai_service.py                  Class     EnvelopeBuilder
ai_service.py            ai_service.py                  Class     RAGValidator
ai_service.py            ai_service.py                  Class     SearchService
qa_service.py            qa_service.py                  Class     UnifiedRetriever
qa_service.py            qa_service.py                  Class     LLMClient
qa_service.py            qa_service.py                  Class     LLMError
qa_service.py            qa_service.py                  Class     RAGValidator
citation_verifier.py     citation_verifier.py           Class     LLMClient
citation_verifier.py     citation_verifier.py           Class     LLMError
review.html              review.html                    Module    frontend/src/pdf_viewer.js
review.html              review.html                    Module    frontend/src/paper_list.js
review.html              review.html                    Module    frontend/src/outline_core.js
review.html              review.html                    Module    frontend/src/outline_editor.js
review.html              review.html                    Module    frontend/src/resizer.js
review.html              review.html                    Module    frontend/src/supplementary_manager.js
review.html              review.html                    Module    frontend/src/paper_importer.js
review.html              review.html                    Module    frontend/src/review.css
index.html               index.html                     Module    frontend/qa.html
index.html               index.html                     Module    frontend/compare.html
index.html               index.html                     Module    frontend/review.html
index.html               index.html                     Module    frontend/tasks.html
download_all_xml.py      download_all_xml.py            Class     PMCXMLDownloader
build_xml_db.py          build_xml_db.py                Module    scripts/parse_pmc_xml.py
```

### 3.4 跨服务 / 外部 HTTP 调用（`HTTP_CALLS` 边，53 条）

**A. 前端 → 后端（27 条，`fetch`）**

| 前端函数 | URL |
|---|---|
| `loadPapers` | `/api/papers` |
| `doSearch` | `/api/retrieve?q={}&top_paragraphs=6&top_figures=3` |
| `doSearch` | `/api/search/hybrid?q={}&top_k=30&use_online=true&online_max=30` |
| `downloadSelectedOnline` | `/api/search/download_online` |
| `pollDownloadStatus` | `/api/search/download_status?task_id={}` |
| `openHistoryModal` | `/api/search/download_history?limit=20` |
| `retryTaskFailed` | `/api/search/retry_download` |
| `retryFailedDownloads` | `/api/search/retry_download` |
| `clearHistory` | `/api/search/clear_download_history` |
| `updateHistoryBadge` | `/api/search/download_history?limit=50` |
| `refreshQueueStatus` | `/api/search/download_queue` |
| `checkStatus` | `/api/qa/status` |
| `doAsk` | `/api/qa/ask` |
| `restoreRunningTask` | `/api/review/running_task` |
| `parseAndOpenPaper` / `autoParseUnparsedPapers` / `triggerParse` | `/api/papers/parse` |
| `loadLocalPapers` | `/api/papers/local` |
| `loadAbstracts` | `/api/abstracts/list?page=1&page_size=50` |
| `loadAbstract` | `/api/abstracts/{id}` |
| `handleGenerateOutline` | `/api/review/outline?topic={}&max_papers={}&review_type=narrative&language=en` |
| `handleGenerateOutline` | `/api/review/cancel/{}` |
| `pollTaskStatus` | `/api/review/task/{}` |
| `handleAssignPapers` | `/api/review/assign_papers` |
| `handleSearchAndAssign` | `/api/review/search_and_assign` |
| `handleGenerateReview` | `/api/review/generate` |
| `handleSaveOutline` | `/api/review/outline/save` |
| `loadSavedOutlines` | `/api/review/outline/saved` |
| `handleTemplateSelect` / `handleLoadOutline` | `/api/review/outline/saved/{}` |
| `loadReview` | `/api/review/{id}` |
| `generateReview` | `/api/review/generate?topic={}&max_papers={}` |
| `selectSentence` | `/api/review/{id}/sentence/{sid}` |
| `handleImport` | `/api/papers/import` |
| `associateSupplementary` | `/api/papers/{id}/supplementary/link` |
| `addAnnotation` / `deleteAnnotation` | `/api/papers/{id}/annotate` |
| `loadOverlays` | `/api/papers/{id}/annotations?page={}` |
| `loadXmlFullText` | `/api/papers/{id}/fulltext` |
| `loadList` / `handleFileUpload` | `/api/papers/{id}/supplementary` |
| `deleteFile` | `/api/papers/{id}/supplementary/{sid}?delete_file=0` |

**B. 后端 → 外部服务（9 条）**

| 调用方 | 目标 URL |
|---|---|
| `get_journals_from_openalex` | `https://api.openalex.org/sources` |
| `find_pdf_url` | `https://api.unpaywall.org/v2/{}` |
| `crossref_lookup` | `https://api.crossref.org/works` |
| `check_ai_models` | `http://localhost:11434/api/tags` |
| `OllamaClient.is_available`（Method） | `{host}/api/tags` |
| `OllamaClient.list_models`（Method） | `{host}/api/tags` |
| `is_alive`（Method） | `{self.api_url}/isalive` |
| `get_protocol`（Method） | `{base}/protocols/{}` |
| `create_app` | `app.register_blueprint` → `/api/papers`、`/api/search`、`/api/ai` |

**C. 前端 → 后端一对多汇总（去重后 22 个唯一端点）**

`/api/papers`、`/api/papers/local`、`/api/papers/parse`、`/api/papers/import`、`/api/papers/{id}/fulltext`、`/api/papers/{id}/supplementary`、`/api/papers/{id}/supplementary/link`、`/api/papers/{id}/supplementary/{sid}`、`/api/papers/{id}/annotate`、`/api/papers/{id}/annotations`、`/api/abstracts/list`、`/api/abstracts/{id}`、`/api/retrieve`、`/api/search/hybrid`、`/api/search/download_online`、`/api/search/download_status`、`/api/search/download_queue`、`/api/search/download_history`、`/api/search/retry_download`、`/api/search/clear_download_history`、`/api/qa/ask`、`/api/qa/status`、`/api/review/*`（outline/generate/assign/search_and_assign/task/cancel/running_task/`{id}`/sentence）

### 3.5 图数据事实与限制

| 事实 | 数值/说明 |
|---|---|
| `CALLS` 边总数 | 2,869 |
| `CALLS` 跨文件可解析比例 | 低：`services/` 内部仅 7 组文件对，且全部为同文件自调用；跨文件样本集中在 `api_server.py → services/*` 与页面内联脚本 |
| `Route` 节点 | 82 个，节点属性**仅含 `method`**，**无 `path`/`handler` 属性**，故 `get_architecture` routes 段 path/handler 列为空 |
| 路由真实来源 | 源码 `@app.route` / `@*_bp.route` 装饰器（70 条，见 3.2） |
| `IMPORTS` 边 | 128 条，`File → Module/Class/Function`；**无 `File → File` 形态** |
| `doc_links` | 429 条 `MENTIONS`；未解析：ambiguous 340 / below_bar_tier 99 / missing 37 |
| 语义边 | `SIMILAR_TO` 75、`SEMANTICALLY_RELATED` 64 |
| 数据流边 | `DATA_FLOWS` 36、`WRITES` 1,022 |
| 状态 | `ready`，watch 已开启（5,000ms 轮询） |

---

## 4. 采集限制声明

1. `get_architecture(all)` 的 `routes` 段只输出 20 条且 `path`/`handler` 为空；本文 3.2 节的路由清单来自**源码装饰器检索**，与图输出分列，未合并判定。
2. 5 个 `docs/*.html` 架构图文件的部分行段未被完整解析（见 1.4），涉及行号已列出。
3. `data/`、`.git/`、`venv_sciPal_py312/` 等 25 个目录与 465 个文件按 `.gitignore` 规则**未进入索引**（by design），运行期数据与依赖不在骨架范围内。
4. `CALLS` 边对跨文件调用的解析覆盖率偏低，本文的"模块调用链"以 `api_server.py` 出向调用 + `IMPORTS` + `HTTP_CALLS` 三类事实共同呈现，不提供跨模块完整调用树。
5. 本文为静态快照（HEAD `68c5a5c`），不含运行时行为、动态分派与反射调用。

---

*本文件由阶段一工单生成，内容为原始采集事实，不含架构判断与改造建议。*
