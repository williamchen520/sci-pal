> 🗺️ **Architecture and route map:** [docs/架构与路由全景图.md](docs/架构与路由全景图.md) — 26 blueprints / 185 API routes

# SciPal — Retrieval-Augmented Research Workbench

> **Status: active development / PG-only.** No stable release.  
> Do not use for clinical or regulated decisions.

**English** | [简体中文](README.zh-CN.md)

SciPal is a locally deployable system for literature search, structured evidence extraction, systematic review and traceable writing. Its core is a deterministic retrieval layer: pgvector recall, PostgreSQL full-text search, reciprocal-rank fusion (RRF), cross-encoder reranking and adaptive context expansion.

Generation is optional and pluggable: a small local model for orchestration, a cloud or DSH model for reasoning.

---

## Architecture

```text
Browser / DSH
    │ HTTP / MCP
    ▼
Flask API (26 blueprints, 185 API routes)
    │
    ├─ services/search        pgvector + PG FTS + RRF + rerank
    ├─ services/review        reviews + systematic review
    ├─ services/claims        claim cards + evidence
    ├─ services/projects      projects / experiments / runs
    ├─ services/watch         monitoring + digest
    └─ build_db/*             parsing, JATS import, PG writes
    │
    ▼
PostgreSQL 16 + pgvector
    + documents/ (PDF / XML)
    + packs/
```

Retired from runtime:

```text
SQLite research.db    archived, not mounted, not created
Chroma                archived, not initialized
```

---

## Technology Stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12, Flask 3 |
| Primary store | PostgreSQL 16 |
| Vector | pgvector + HNSW |
| Full text | PostgreSQL GIN `tsvector`; optional ParadeDB path |
| Embeddings | `BAAI/bge-base-en-v1.5` |
| Reranker | `BAAI/bge-reranker-base` |
| Parsing | PyMuPDF, Docling, GROBID, MinerU, JATS XML |
| Generation | OpenAI-compatible cloud API, Ollama fallback, DSH optional |
| Frontend | vanilla HTML/CSS/JS + PDF.js |
| Deployment | Docker Compose: app + watch-cron + Caddy + PostgreSQL |

---

## Current Data

| Item | Value |
|---|---:|
| papers | 10,102 |
| paragraphs | 331,263 |
| sentences | 1,492,661 |
| sections | 124,216 |
| paragraph embeddings | 320,928 |
| summaries | 69,128 |
| HNSW index | 1.235 GB, valid |
| PostgreSQL size | ~5.4 GB |

Archived:

```text
research.db   I:\_archive\research.db-20261107
Chroma        I:\_archive\chroma-20261107
```

---

## Capabilities

| Capability | Description |
|---|---|
| Literature search | pgvector + PG FTS, RRF, rerank, section expansion |
| Structured parsing | PDF engines + native JATS XML |
| Section / paragraph / sentence tree | explicit IDs, page and bbox |
| Citation / figure / table links | sentence-level provenance |
| Sentence traceability | `/api/papers/<id>/trace`, page crops |
| Evidence envelopes | parent context + matched sentences + links |
| RAG QA | citations, refusal, local or cloud models |
| Review generation | outline → section retrieval → drafting → verification |
| Systematic review | screening, PRISMA, evidence, risk of bias, reports |
| Claims | claim cards, qualifiers, supporting/opposing evidence |
| Projects / experiments | members, runs, revisions, audit, signatures |
| Literature monitoring | profiles, journals, runs, digests |
| Multi-user isolation | users, workspaces, roles |
| Domain packs | taxonomy / section types / evidence schema |
| Plugins | ingest tracking, ports, experimental GraphRAG/RAPTOR |

---

## Quick Start

### Docker Compose

```bash
cp deploy/.env.example deploy/.env
# edit SCIPAL_PG_DSN, SCIPAL_SECRET_KEY
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1/api/health
```

Services:

```text
app         Flask API
postgres    PostgreSQL 16 + pgvector
watch-cron  literature monitoring scheduler
caddy       reverse proxy
```

### Local Development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
set SCIPAL_PG_DSN=postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
python api_server.py
```

Development server only. For production use:

```text
APP_MODE=PROD_MODE  -> gunicorn
```

---

## Configuration

Required:

```text
SCIPAL_PG_DSN=postgresql://user:pass@host:5432/scipal_bench
SCIPAL_SECRET_KEY=<random>
```

PG-only defaults:

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_FTS_BACKEND=postgres
SCIPAL_SEARCH_META_BACKEND=postgres
SCIPAL_SQLITE_QUERY_ONLY=1
SCIPAL_ABSTRACTS_BACKEND=postgres
SCIPAL_PROJECTS_BACKEND=postgres
SCIPAL_RUNS_BACKEND=postgres
SCIPAL_EXPERIMENTS_BACKEND=postgres
SCIPAL_REVIEWS_BACKEND=postgres
SCIPAL_SYSTEMATIC_BACKEND=postgres
SCIPAL_CLAIMS_BACKEND=postgres
SCIPAL_NOTES_BACKEND=postgres
SCIPAL_TASKS_BACKEND=postgres
SCIPAL_PAPERS_READ_BACKEND=postgres
SCIPAL_INGEST_PG_ONLY=1
SCIPAL_TENANCY_PG_ONLY=1
```

Auth:

```text
SCIPAL_AUTH_REQUIRED=1
```

---

## API Examples

```bash
curl http://127.0.0.1/api/health

curl -X POST http://127.0.0.1/api/evidence/search \
  -H "Content-Type: application/json" \
  -d '{"query":"hepatocellular carcinoma","top_paragraphs":5}'

curl "http://127.0.0.1/api/papers?limit=5"
```

Main groups:

```text
/api/papers
/api/search
/api/evidence
/api/qa
/api/reviews
/api/review-projects
/api/projects
/api/experiments
/api/claims
/api/watch
/api/workspaces
/api/tasks
```

---

## Repository Layout

```text
api_server.py              Flask app and blueprint registration
routes/                    26 blueprints
services/                  search, review, claims, projects, watch, ...
build_db/                  parsers, JATS import, PG writers
plugins/                   optional plugins
frontend/                  HTML/CSS/JS
docs/                      architecture, migration, operations
scripts/                   smoke tests, audits, backfills
deploy/                    Dockerfile, compose, env
tests/                     pytest suites
```

---

## Testing

```bash
pytest

python scripts/smoke_http.py        # A: 31 light GETs
python scripts/smoke_group_b.py     # B: 14 medium GETs
python scripts/smoke_group_c.py     # C: 5 heavy GETs
```

Current smoke result:

```text
50 routes / 0 5xx
research.db absent
```

Retrieval:

```text
20-question regression   Recall@10 0.675 / nDCG@10 0.461
SciFact 300              Recall@10 0.8669 / nDCG@10 0.7458
```

---

## Known Limitations

```text
12 title-duplicate groups with different PMCIDs are not merged
300-question full-text gold set is deferred
GraphRAG / RAPTOR remain plugin experiments
Client ingest tracking is not wired to the real import UI
Base image still contains chromadb package although runtime does not use it
Some cold POST endpoints are not covered by automated smoke tests
```

---

## Documentation

| Document | Purpose |
|---|---|
| [Architecture and Routes](docs/架构与路由图.md) | system flow and route map |
| [Module Manual](docs/开发-模块手册.md) | module responsibilities and entry points |
| [PG-only Final Report](docs/PG-only迁移总报告-2026-11-08.md) | migration decisions and verification |
| [ARCHITECTURE.json](ARCHITECTURE.json) | machine-readable architecture |
| [Smoke Plan](docs/全站端点分层烟测计划.md) | layered endpoint testing |

---

## License

See [LICENSE](LICENSE).
