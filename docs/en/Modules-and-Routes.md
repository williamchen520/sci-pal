# Developer Guide: Modules and Routes

> For second-time contributors.  
> Goal: find the module, entry point, and files for a feature without reading the full architecture first.

## 0. How to use this guide

```text
Start with the module index
-> find the feature
-> read its responsibilities, route prefix, key files
-> use Architecture and Routes only for cross-module data flow
```

Related docs:

- [Architecture and Routes](Architecture-and-Routes.md) — system-wide data flow
- [Research Logs Index](../Research_Logs_Index.md) — why the code changed
- [Collaboration rules](../协作规范.md) — commit and merge conventions

---

## 1. Module index

| Module | Route prefix | Key files | One-line purpose |
|---|---|---|---|
| Core / System | `/api/health`, `/api/retrieve`, `/api/graph`, `/api/communities` | `routes/core.py`, `routes/system.py` | health, retrieval entry, graph stats |
| Search | `/api/search` | `routes/search.py`, `services/search/` | local/online search, download, dedup, RRF |
| Papers | `/api/papers` | `routes/papers.py`, `routes/papers_actions.py`, `services/papers/` | paper detail, parse, upload, trace |
| Ingest | `/api/ingest` | `routes/ingest.py`, `services/search/ingest.py` | PMC batch download, parse, write, embed |
| Evidence / QA | `/api/evidence`, `/api/qa`, `/api/agentic`, `/api/verify` | `routes/evidence.py`, `routes/qa.py`, `services/qa/` | evidence packs, QA, answer verification |
| References / Abstracts | `/api/references`, `/api/abstracts` | `routes/references.py`, `routes/abstracts.py` | references, abstract DB |
| Watch | `/api/watch` | `routes/watch.py`, `services/watch/` | journal monitoring, digests, feedback |
| Claims | `/api/claims` | `routes/claims.py`, `services/claims/` | claim cards, evidence, decisions |
| Reviews | `/api/reviews`, `/api/review`, `/api/review-projects` | `routes/reviews.py`, `routes/review_actions.py`, `routes/systematic_review.py`, `services/review/` | review generation, systematic review projects |
| Projects | `/api/projects` | `routes/projects.py`, `services/tenancy/` | projects and members |
| Experiments | `/api/experiments`, `/api/runs` | `routes/experiments.py`, `routes/runs.py` | experiments, runs, signatures |
| Tenancy | `/api/auth`, `/api/workspaces` | `routes/tenancy.py` | auth, users, workspaces, isolation |
| Notes | `/api/notes` | `routes/notes.py` | paper notes |
| Domain packs | `/api/domain-packs` | `routes/domain_packs.py`, `packs/` | declarative domain packs |
| Guard | `/api/guard` | `routes/guard.py`, `services/guard/` | terminology guard |
| Data | `/api/data` | `routes/data.py`, `services/data/` | local tabular profile/aggregate/artifacts |
| Tasks | `/api/tasks` | `routes/tasks.py` | unified async task status |
| Protocols | `/api/protocols` | `routes/protocols.py` | Protocols.io / lab protocols |

---

## 2. Module details

### 2.1 Core / System

```text
routes/core.py
routes/system.py
services/retrieval/
services/graph/
```

Responsibilities:

```text
/api/health          health check
/api/retrieve        retrieval debugging entry
/api/graph           citation / semantic graph
/api/communities     community detection results
```

Changes here usually affect everything; start with `services/retrieval`.

### 2.2 Search

```text
routes/search.py
routes/search_downloads.py
services/search/
  hybrid.py
  ingest.py
  online_downloader.py
  preprint_ingest.py
  dedup.py
```

Responsibilities:

```text
/api/search/hybrid           local hybrid retrieval
/api/search/online           online retrieval
/api/search/download_online  online download
/api/search/download_status  download task status
```

Key concepts:

```text
paragraph FTS      production ranking
vector recall      Chroma paragraphs / contextual
RRF                fusion
rerank             bge-reranker
MMR / soft cap     experimental switches
```

### 2.3 Papers

```text
routes/papers.py
routes/papers_actions.py
services/papers/
  pg_writes.py
  preflight.py
build_db/parse_service.py
build_db/db_writer.py
```

Responsibilities:

```text
/api/papers              list
/api/papers/<id>         detail
/api/papers/parse        parse local PDF
/api/papers/parse_async  async parse
/api/papers/import       import
/api/papers/<id>/trace   sentence trace
```

PDF / preprint write path:

```text
upload / parse
-> parse_service
-> DatabaseWriter.insert_paper
-> preflight.audit_and_repair
-> PostgreSQL + SQLite
```

### 2.4 Ingest

```text
routes/ingest.py
services/search/ingest.py
build_db/import_jats.py
```

Responsibilities:

```text
POST /api/ingest             submit a PMC batch
GET  /api/ingest/<task_id>   poll status
POST /api/ingest/<id>/cancel cancel
POST /api/embed              single-writer Chroma bridge
```

Flow:

```text
download batch
-> parse JATS
-> preflight
-> SQLite transaction
-> PG write_papers_batch
-> embed
```

### 2.5 Evidence / QA

```text
routes/evidence.py
routes/qa.py
services/qa/
services/search/evidence.py
```

Responsibilities:

```text
/api/evidence/search   evidence packs
/api/qa/ask            question answering
/api/agentic/search    multi-hop retrieval
/api/verify            answer citation verification
```

### 2.6 Watch

```text
routes/watch.py
services/watch/
  discovery.py
  runner.py
  repo.py
  pg_writes.py
scripts/run_watch_due.py
```

Responsibilities:

```text
/api/watch/profiles              profile CRUD
/api/watch/profiles/<id>/run     trigger a run
/api/watch/profiles/<id>/latest  latest digest
/api/watch/runs/<id>/digest.md   digest markdown
```

### 2.7 Claims

```text
routes/claims.py
services/claims/
  service.py
  pg_writes.py
```

Responsibilities:

```text
/api/claims                 list / create
/api/claims/<id>/evidence   supporting / opposing evidence
/api/claims/<id>/decision   adjudication
```

### 2.8 Reviews

```text
routes/reviews.py
routes/review_actions.py
routes/systematic_review.py
services/review/
```

Responsibilities:

```text
/api/reviews                 review generation
/api/review-projects         systematic review projects
/api/review-projects/<id>/... PRISMA, screening, evidence table
```

### 2.9 Projects / Experiments / Tenancy

```text
routes/projects.py
routes/experiments.py
routes/runs.py
routes/tenancy.py
services/tenancy/
```

Responsibilities:

```text
/api/projects        projects
/api/experiments     experiments
/api/runs            experiment runs
/api/auth            login
/api/workspaces      workspaces
```

Isolation:

```text
papers.workspace_id
projects / project_members
experiments / experiment_runs
```

### 2.10 Notes / Domain packs / Guard / Data / Tasks / Protocols

```text
routes/notes.py
routes/domain_packs.py
routes/guard.py
routes/data.py
routes/tasks.py
routes/protocols.py
```

Independent edge modules; changing one usually does not affect the retrieval main path.

---

## 3. Route prefix quick reference

```text
/api/health
/api/retrieve
/api/graph
/api/communities
/api/search
/api/papers
/api/ingest
/api/embed
/api/evidence
/api/qa
/api/agentic
/api/verify
/api/references
/api/abstracts
/api/watch
/api/claims
/api/reviews
/api/review
/api/review-projects
/api/projects
/api/experiments
/api/runs
/api/auth
/api/workspaces
/api/notes
/api/domain-packs
/api/guard
/api/data
/api/tasks
/api/protocols
```

List the live route table:

```powershell
python -c "import api_server; [print(r.rule, r.endpoint) for r in sorted(api_server.app.url_map.iter_rules(), key=lambda x: x.rule)]"
```

---

## 4. Where to add a module

```text
1. routes/<name>.py
   HTTP parsing, auth, error mapping only

2. services/<domain>/
   business logic, SQL, external APIs

3. Async work
   services/<domain>/task_manager.py
   or reuse services/review/task_manager.py

4. New tables
   build_db/<domain>_schema.py
   migrations must be idempotent
```

Register blueprints in `api_server.py`; do not mutate the global app inside a new module.

---

## 5. Where to add tests

```text
tests/test_<module>_routes.py      route contract
tests/test_<module>_service.py     business logic
tests/test_<module>_pg_writes.py   PG write path
```

Every PR should cover:

```text
success path
one failure path
one auth/isolation path when user data is involved
```

---

## 6. Data layer

```text
PostgreSQL
  papers / paragraphs / sentences / sections
  projects / experiments / runs
  claims / reviews
  watch
  tenancy

SQLite
  FTS5 mirror
  legacy build mirror
  local compatibility

Chroma
  paragraphs
  paragraphs_contextual
  papers
  section_summaries
  figures
  tables
```

Write-path rule:

```text
runtime writes go to PG first
SQLite is FTS / legacy mirror
new write paths start in services/papers/pg_writes.py
```

---

## 7. Minimum onboarding path

```text
1. run health
2. call /api/evidence/search once
3. read routes/evidence.py -> services/search
4. read tests/test_evidence_routes.py
5. change a response field that does not touch a write path
6. run the matching tests
```

Do not start with the 100+ experiment records under `docs/`.
