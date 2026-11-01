# SciPal — A Retrieval-Augmented Research Workbench

**English** | [简体中文](README.zh-CN.md)

SciPal is a locally deployable system for searching scientific literature, parsing papers into structured evidence, and producing traceable literature reviews. Its core is a **deterministic retrieval layer** — vector search, FTS5/BM25, reciprocal-rank fusion (RRF), cross-encoder reranking, query routing, and adaptive context expansion. For generation, we recommend a **small local model for orchestration plus a cloud or DSH model for reasoning**.

> Current version: **V33.96** (2026-10-31)  
> Python 3.12 · Flask · ChromaDB · SQLite · OpenAI-compatible cloud APIs / Ollama  
> Vanilla HTML/CSS/JS frontend (no framework); DSH can serve as an optional reasoning layer.

---

## ⚠️ Work in Progress

1. SciPal is under active development. No stable release has been published.
2. The main branch contains known bugs, unstable APIs, and code paths that have not been fully tested.
3. **Do not deploy the current code in production**, in clinical or regulated research workflows, or anywhere data loss would matter.
4. If you ignore this warning and use development code in production, you are responsible for any resulting data loss, service failure, or other damage. The authors accept no liability.

---

## Large-Scale and Concurrent Testing Policy

> **Use PostgreSQL for any benchmark with more than 100 papers or with concurrent workers. Do not use SQLite for high-concurrency testing.**
>
> SQLite is allowed only for small, single-process local checks (≤100 papers), and only when `SCIPAL_BENCH_ALLOW_SQLITE=1` is set explicitly.

Default benchmark connection string:

```text
postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
```

Override it with:

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "postgresql://user:pass@host:5432/db"
```

Small local checks only:

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "sqlite:///data/bench_local.db"
$env:SCIPAL_BENCH_ALLOW_SQLITE = "1"
```

Notes:

- The operational database is still SQLite; the PostgreSQL business backend is not complete yet.
- The policy is **fail-fast**: large or concurrent benchmarks fail instead of silently falling back to SQLite.
- See [docs/benchmark-PostgreSQL策略.md](docs/benchmark-PostgreSQL策略.md) (Chinese) for details.

---

## What It Does

| Capability | Description |
|---|---|
| Literature search | Dual recall with vectors and FTS5, RRF fusion, cross-encoder reranking, paragraph-to-section expansion |
| Structured parsing | Three PDF engines (Docling / GROBID / MinerU) plus native JATS XML import |
| Section / paragraph / sentence tree | Explicit `sections.parent_id`, `paragraphs.section_id`, and sentence-level page/bbox metadata |
| Citation and figure/table links | Sentence ↔ citation/figure/table links with provenance and confidence |
| Sentence traceability | `/api/papers/<id>/trace`, highlighted page crops, and `frontend/trace.html` |
| RAG question answering | Evidence envelopes, citations, and switchable local 7B or cloud models |
| Adaptive contextual retrieval | Original paragraph index for simple questions; contextual index for complex ones; enabled by default |
| Sentence seeds | `sentences_fts` supplies paragraph candidates; `SCIPAL_SENTENCE_SEEDS=1` improves recall at roughly 3.6× latency |
| Domain adaptation | `domain_profiles` + `paper_domains` + soft routing; off by default |
| Answer-level evaluation | Async QA with coverage, citation, and refusal metrics; 100-question cloud run: coverage 0.7733, refusal 1.00 |
| External evaluation | SciFact 100 claims: doc recall 0.97 / sentence recall 0.97 / MRR 0.828; LitQA2 20-question smoke test |
| Refusal and grounding | Domain-aware refusal; token-overlap, cross-encoder, and LLM grounding remain experimental switches |
| QA budget adaptation | Simple and complex questions default to top-10; `SCIPAL_QA_COMPLEX_TOPK=20` raises complex coverage |
| Review generation | Outline → section-level retrieval allocation → section drafting → evidence/claim matrix → iterative scoring |
| Online search and ingest | PubMed / PMC search, async download, incremental ingest, queue/history/retry |
| Literature sources | Europe PMC batch, arXiv/bioRxiv/medRxiv, Crossref/OpenAlex/Unpaywall |
| Metadata backfill | Crossref DOI → Crossref title → OpenAlex title; 99.9%+ coverage |
| Citation graph | `paper_links`: cites / cited_by / similar |
| Literature monitoring | Multiple profiles, journal discovery, incremental fetch, deduplication, weekly digests, item feedback, and `watch-cron` scheduling |
| Multi-user isolation | users / workspaces / memberships; roles owner/pi/member/viewer; isolation for papers, notes, projects, and experiments |
| Projects and experiments | Project members, experiments, two-level runs, revisions, field audit, electronic signatures, and PI access requests |
| Domain packs | Declarative packs (taxonomy / section types / evidence schema / prompts); `/packs.html` |
| Claim pilot | Claim cards, qualifiers, supporting/opposing evidence, FTS/semantic retrieval, NLI, verdict events, writing briefs |
| Plugin ports M0/M1/M2 | `services/plugins` + `plugins/` manifest/port schema/adapter; JSONL provenance; ClaimVerifier and Retriever ports |
| Benchmark DB policy | PostgreSQL by default; SQLite disabled above 100 papers or under concurrency; explicit opt-in for small runs |
| DB adapter P1 | SQLite default; PostgreSQL schema and adapter opt-in; no data migration and no read-path switch |
| Deployment | Docker Compose (app + watch-cron + Caddy), backups, offline bundle |
| Experimental protocols | Protocols.io search/import; Dockstore / bio.tools / nf-core |

## Architecture

![SciPal architecture](docs/图-SciPal芯片架构.png)

For module, route, and data-flow diagrams, see **[Architecture and Routes](docs/en/Architecture-and-Routes.md)** (English) or [架构与路由图](docs/架构与路由图.md) (Chinese).

```text
DSH desktop / browser
   │ MCP / HTTPS
   ▼
Flask API (26 blueprints under routes/*, ~180 routes)
   │
services/* (retrieval, QA, reviews, guard, source adapters)
   │
build_db/* (parsing, JATS import, structure rebuild, database writes)
   │
SQLite research.db + ChromaDB + documents/ + documents_xml/
```

## Technology Stack

- Backend: Python 3.12 · Flask 3 · flask-cors · pydantic 2 · networkx
- Retrieval: ChromaDB · sentence-transformers · FTS5 (BM25) · RRF · bge-reranker
- PDF: PyMuPDF · Docling · GROBID · MinerU (on demand, with quality gates)
- XML: PMC / Europe PMC JATS (`<sec>` / `<ref-list>` / `<xref>`)
- LLMs: OpenAI-compatible cloud API (recommended for reasoning) + local Ollama (orchestration/fallback); DSH can take over reasoning
- Frontend: vanilla HTML/CSS/JS + PDF.js (viewer / compare / trace / projects / reviews / watch / packs / claims)
- Deployment: Docker Compose (app + watch-cron + Caddy) · single-node SQLite · persistent data volume

### Models

| Model | Role |
|---|---|
| `deepseek-chat` (cloud) | Recommended: QA, reviews, claim verification |
| `qwen2.5:3b` | Local lightweight: intent, routing, orchestration |
| `qwen2.5:7b-instruct-q4_K_M` | Local fallback: offline QA/reviews (Q4 quantized) |
| `BAAI/bge-base-en-v1.5` | Embeddings |
| `BAAI/bge-reranker-base` | Cross-encoder reranking |
| `scispacy en_ner_bionlp13cg_md` | Biomedical entity recognition |
| Docling / TableFormer | Layout, tables, sections |
| MinerU 4.x | Scanned/complex-layout fallback |
| GROBID (CRF/Full) | Metadata, structured citations, in-text citation locations |

## Data Scale (`research.db`)

| Table | Rows |
|---|---:|
| papers | 3,310 (JATS XML 3,218 + PDF 83 + others) |
| paragraphs | 167,388 |
| sentences | 862,677 (PDF sentence bbox: 61,739) |
| sections | 69,128 |
| citations | 182,817 (91.5% with sentence-level locations) |
| figures / tables | 13,471 / 4,922 |
| sentence_links | 296,867 (JATS 291,857 + GROBID 3,292) |
| paper_links | 164,802 |

## Quick Start

```powershell
# 1. Dependencies
python -m venv venv_sciPal_py312
venv_sciPal_py312\Scripts\pip install -r requirements.txt

# 2. Start Flask on port 5000
venv_sciPal_py312\Scripts\python.exe api_server.py

# 3. Optional parser services (three PDF engines)
powershell -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1

# 4. Tests (with consecutive-failure stop)
venv_sciPal_py312\Scripts\python.exe scripts\run_tests_guarded.py

# Equivalent standard command (no stop-loss)
venv_sciPal_py312\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Common environment variables:

```powershell
# Recommended: cloud reasoning
$env:SCIPAL_LLM_PROVIDER = "openai"
$env:SCIPAL_LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:SCIPAL_LLM_MODEL = "deepseek-chat"
$env:SCIPAL_LLM_API_KEY = "sk-..."

# Or local Ollama (offline/orchestration)
$env:SCIPAL_LLM_PROVIDER = "ollama"
$env:SCIPAL_LLM_MODEL = "qwen2.5:7b-instruct-q4_K_M"

$env:SCIPAL_GROBID_URL = "http://127.0.0.1:8070"
$env:SCIPAL_GROBID_URL_FULL = "http://127.0.0.1:8071"
$env:MINERU_HOME = "D:\mineru_home"
```

On Linux/macOS, use `python3` and the corresponding `venv/bin/python` paths. The project currently targets Windows first; cross-platform notes are in [Windows开发警示与跨平台规范.md](docs/Windows开发警示与跨平台规范.md) (Chinese).

## Repository Layout

```text
sci-pal/
├─ api_server.py             Flask entry point (blueprints; static routes only)
├─ routes/                   26 blueprints: core/search/papers/reviews/qa/watch/claims/...
├─ services/
│  ├─ search/                hybrid retrieval, rerank, context expansion, source adapters
│  ├─ qa/                    QA and evidence envelopes
│  ├─ review/                review generation, LLM client, tasks
│  ├─ watch/                 profile / run / digest / scheduler
│  ├─ domain_packs/          pack loader / validator / CLI
│  ├─ claims/                retrieval / semantic / NLI / service
│  ├─ plugins/               contracts / registry / runner
│  ├─ tenancy/               users / workspaces / roles
│  ├─ projects/ experiments/ projects / experiments / runs / audit / signatures
│  ├─ quality/               guard, terminology checks
│  └─ pdf/ workflow/ utils/
├─ build_db/                 parsers, JATS import, structure rebuild, DB writers
├─ mcp_server/               search / generate / guard (thin MCP forwarding)
├─ packs/                    domain packs (biomed-oncoimmuno)
├─ plugins/                  plugin manifests / port schemas / adapters
├─ eval/                     retrieval, QA, and plugin benchmark scripts
├─ frontend/                 viewer / compare / trace / projects / reviews / watch / packs / claims
├─ docs/                     architecture, data, and design documents
├─ tests/                    750 tests
├─ documents/                PDFs
├─ documents_xml/            JATS XML
├─ data/                     research.db, Chroma
└─ scripts/                  service and maintenance scripts
```

## API Groups

| Group | Prefix |
|---|---|
| Auth / workspaces | `/api/auth/*` `/api/workspaces/*` |
| Retrieval | `/api/retrieve` `/api/search/*` |
| Papers | `/api/papers/*` (parse, PDF, attachments, annotations, trace) |
| QA | `/api/qa/*` `/api/agentic/*` |
| Reviews | `/api/review/*` `/api/reviews/*` |
| Literature monitoring | `/api/watch/*` |
| Domain packs | `/api/domain-packs/*` |
| Claims | `/api/claims/*` |
| Projects / experiments | `/api/projects/*` `/api/experiments/*` `/api/runs/*` |
| Quality | `/api/guard/*` |
| Ingest / tasks | `/api/ingest/*` `/api/tasks/*` |
| Other | `/api/protocols/*` `/api/references/*` `/api/abstracts/*` |

The source of truth is `routes/` and `api_server.py`. See [API Reference](docs/en/API-Reference.md) (English) or [接口明细](docs/接口明细.md) (Chinese).

## Tests

```text
750 tests, ~65s
```

Coverage includes retrieval, routing, guard, structure, JATS import, watch, domain packs, claim pilot, multi-user isolation, projects/experiments/runs, and plugin ports.

## Documentation

English:

- [Documentation index](docs/en/README.md)
- [Architecture overview](docs/en/Architecture-Overview.md)
- [Architecture and routes](docs/en/Architecture-and-Routes.md)
- [API reference](docs/en/API-Reference.md)
- [PostgreSQL migration plan](docs/en/plans/PostgreSQL-Migration.md)
- [Multi-user and data isolation plan](docs/en/plans/Multi-User-and-Data-Isolation.md)
- [Domain packs and distribution](docs/en/plans/Domain-Packs-and-Distribution.md)
- [Plugin ports and benchmarks](docs/en/plans/Plugin-Ports-and-Benchmarks.md)
- [Argument workbench plan](docs/en/plans/Argument-Workbench.md)
- [Adaptive retrieval and literature intelligence](docs/en/plans/Adaptive-Retrieval-and-Literature-Intelligence.md)
- [DSH integration and plugins](docs/en/plans/DSH-Integration-and-Plugins.md)
- [Project tracking and ELN](docs/en/plans/Project-Tracking-and-ELN.md)

Chinese:

- [架构与路由图](docs/架构与路由图.md)
- [PDF 三引擎联合解析](docs/PDF解析-三引擎联合.md)
- [P4 sentence-level FTS](docs/数据重建-P4-句子级FTS.md)
- [文献源与 JATS 导入](docs/文献源-JATS与外部源.md)
- [多用户与数据隔离计划](docs/工作计划-多用户与数据隔离.md)
- [去学科化与领域包分发计划](docs/工作计划-去学科化与领域包分发.md)
- [自适应与文献情报计划](docs/工作计划-自适应与文献情报.md)
- [项目跟踪与实验记录计划](docs/工作计划-项目跟踪与实验记录.md)
- [DSH 适配与插件化计划](docs/工作计划-DSH适配与插件化.md)
- [论证工作台改造计划](docs/工作计划-论证工作台改造.md)

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. **Open an issue first**, and make sure the unit tests pass.

## Security

Please do **not** open a public issue for security vulnerabilities. Report them privately to **chenwei-ucas@outlook.com**; see [SECURITY.md](SECURITY.md).

## License

AGPL-3.0-only. See [LICENSE](LICENSE) and [docs/许可证说明.md](docs/许可证说明.md) (Chinese).
