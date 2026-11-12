# SciPal — Retrieval-Augmented Research Workbench

> **Status: active development / PG-only.** No stable release.  
> Do not use for clinical or regulated decisions.

**English** | [简体中文](README.zh-CN.md)

SciPal is a locally deployable system for literature search, structured evidence
extraction, systematic review, and traceable writing. Its core is a deterministic
retrieval layer: pgvector recall, PostgreSQL full-text search, reciprocal-rank
fusion (RRF), optional cross-encoder reranking, and sentence-aware context.

Generation is optional and pluggable: a local model for orchestration, a cloud or
DSH model for reasoning.

---

## Architecture

```text
Browser / DSH / MCP
        │
        ▼
      Caddy
        │  HTTPS, security headers
        ▼
   Flask API (26 blueprints, 204 route+method; 210 with ingest-tracking)
        │
        ├── scipal_core
        │     users / auth / workspaces / projects / experiments
        │     notes / tasks / claims / reviews / audit
        │
        └── scipal_rebuild
              papers / sections / paragraphs / sentences
              paragraph_embeddings / citations / figures / tables
```

Retrieval:

```text
pgvector HNSW + PostgreSQL GIN FTS + RRF
sentence-level evidence
sentence-window context
```

Operations:

```text
worker          long-running jobs
pg-backup       encrypted PostgreSQL dumps
watch-cron      literature monitoring
```

Data ownership is physical, not just a naming convention:

```text
core and corpus are separate PostgreSQL databases
no cross-database foreign keys
logical IDs only (paper_id / user_id)
business reads never hit the corpus database
corpus reads never hit the business database
```

---

## Current Data

| Item | Value |
|---|---:|
| papers | 13,201 |
| paragraphs | 410,270 |
| sentences | 1,780,306 |
| sections | 156,208 |
| paragraph embeddings | 343,546 |
| HNSW index | 1.326 GB, valid |
| PostgreSQL (rebuild) | ~5.5 GB |

---

## Capabilities

| Capability | Description |
|---|---|
| Literature search | pgvector + PG FTS, RRF, optional rerank |
| Structured parsing | PDF engines + native JATS XML |
| Sentence traceability | `/api/papers/<id>/trace`, page/bbox |
| Evidence envelopes | matched sentences + parent context + links |
| RAG QA | citations, refusal, local or cloud models |
| Review generation | outline → section retrieval → drafting → verification |
| Systematic review | screening, PRISMA, evidence, risk of bias |
| Claims | claim cards, qualifiers, supporting/opposing evidence |
| Projects / experiments | members, runs, revisions, audit |
| Literature monitoring | profiles, journals, runs, digests |
| Multi-user isolation | users, workspaces, roles, least-privilege DSNs |
| Domain packs | taxonomy / section types / evidence schema |
| Optional plugins | ingest tracking, experimental GraphRAG/RAPTOR |

---

## Security & Operations

```text
global API auth        session / bearer / internal service token
internal endpoints     /api/ingest, /api/embed require internal token
database roles         core_app / corpus_reader / corpus_writer (no DDL)
environment guard      production rejects loopback/wrong-database DSNs
backups                core every 6h (7d), corpus every 7d (28d)
backup encryption      AES-256-CBC + PBKDF2, files mode 600
restore drill          data + GIN + HNSW validated 2026-11-12
governance gate        high-risk PRs require human approval
```

Do not put production credentials in `.env` files committed to git.

---

## Quick Start

### Docker Compose

```bash
cp deploy/.env.example deploy/.env
# set the DSNs, SCIPAL_SECRET_KEY, and backup passphrase
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1/api/health
```

Required DSNs:

```text
SCIPAL_CORE_DSN            -> scipal_core (business/auth)
SCIPAL_AUTH_DSN            -> scipal_core (auth schema)
SCIPAL_PG_DSN              -> scipal_core (compatibility default)
SCIPAL_PG_CORPUS_DSN       -> scipal_rebuild (read)
SCIPAL_PG_MAIN_READ_DSN    -> scipal_rebuild (read)
SCIPAL_PG_OWNER_DSN        -> scipal_rebuild (write, no DDL)
SCIPAL_PG_INGEST_DSN       -> scipal_rebuild (ingest write)
```

Services:

```text
app         Flask API
postgres    PostgreSQL 16 + pgvector
pg-backup   encrypted dumps
watch-cron  literature monitoring
caddy       reverse proxy / TLS
```

### Local Development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
# configure .env or environment variables
python api_server.py
```

Development server only. For production use `APP_MODE=PROD_MODE` with gunicorn.

---

## Testing

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/smoke_http.py        # A: 27 light GETs
python scripts/smoke_group_b.py     # B: 13 medium GETs
python scripts/check_data_boundary.py
python scripts/validate_arch.py
```

Current known smoke result:

```text
A 27/27 200
B 13/13 200
```

Route count:

```text
26 blueprints / 204 route+method by default
27 blueprints / 210 route+method with SCIPAL_INGEST_TRACKING=1
```

Recorded retrieval results:

```text
SciFact 300        Recall@10 0.8669 / nDCG@10 0.7458
rebuild_20 hybrid  Recall@10 0.7000 / nDCG@10 0.4894
```

---

## Configuration

PG-only defaults:

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_FTS_BACKEND=postgres
SCIPAL_SEARCH_META_BACKEND=postgres
SCIPAL_PAPERS_READ_BACKEND=postgres
SCIPAL_INGEST_PG_ONLY=1
SCIPAL_TENANCY_PG_ONLY=1
SCIPAL_AUTH_REQUIRED=1
SCIPAL_ENV=production
```

Auth-related:

```text
SCIPAL_AUTH_DSN
SCIPAL_INTERNAL_TOKEN
SCIPAL_INTERNAL_USER_ID
SCIPAL_INTERNAL_WORKSPACE_ID
```

Backup:

```text
SCIPAL_BACKUP_PASSPHRASE
```

Do not commit real values.

---

## Repository Layout

```text
api_server.py              Flask app and blueprint registration
routes/                    26 blueprints
services/                  search, review, claims, projects, watch, ...
services/db/               connection factories, env guard, pool
eval/                      retrieval/QA evaluation, public dataset loaders
build_db/                  parsers, JATS import, PG writers
plugins/                   optional plugins
frontend/                  HTML/CSS/JS
docs/                      architecture, migration, operations, research
scripts/                   smoke, audits, backfills, governance gate
deploy/                    Dockerfile, compose, env, SQL
tests/                     unittest/pytest suites
config/                    governance gates
```

---

## Documentation

| Document | Purpose |
|---|---|
| [Architecture and Routes](docs/en/Architecture-and-Routes.md) | routes, layers, data flow |
| [Module Manual](docs/en/Modules-and-Routes.md) | module responsibilities |
| [Architecture JSON](ARCHITECTURE.json) | machine-readable contract |
| [Data isolation audit](docs/数据层隔离审计.md) | table/DSN ownership |
| [Backup strategy](docs/备份策略-双库.md) | backup and restore |
| [Restore drill 2026-11-12](docs/恢复演练-20261112.md) | data + GIN + HNSW validation |
| [Code review 2026-11-12](docs/代码审查-20261112.md) | P0/P1 findings |
| [Governance gates](docs/工程治理门禁规范.md) | preflight and approval |
| [Public evaluation sets](docs/公共测试集选型.md) | SciFact / LitQA2 / QASPER |

---

## Known Limitations

```text
LitQA2 local coverage: 82/199 evaluable
QASPER evidence is paragraph-level, not sentence-level
A full-text benchmark for SciFact claims is not available
GraphRAG / RAPTOR remain experiments, not core paths
Client ingest tracking requires the separate migration
No stable release; APIs and schemas may change
```

---

## License

See [LICENSE](LICENSE).
