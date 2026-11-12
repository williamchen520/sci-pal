# Architecture Overview

> **Current state — 2026-11-12**  
> PG-only, physically separated `scipal_core` / `scipal_rebuild`.

This is the short English entry point. For the machine contract see
[ARCHITECTURE.json](../../ARCHITECTURE.json); for the Chinese route map see
[架构与路由全景图](../架构与路由全景图.md).

---

## 1. Runtime shape

```text
Browser / DSH / MCP
        │
        ▼
      Caddy
        │ HTTPS + security headers
        ▼
   Flask API (26 blueprints; 204 route+method)
        │
        ├── scipal_core
        │     users / auth / workspaces / memberships
        │     projects / experiments / notes / tasks
        │     claims / reviews / audit
        │
        └── scipal_rebuild
              papers / sections / paragraphs / sentences
              paragraph_embeddings / citations / figures / tables
        │
        ├── worker       long-running jobs
        ├── pg-backup    encrypted dumps
        └── watch-cron   literature monitoring
```

With `SCIPAL_INGEST_TRACKING=1`, the optional ingest-tracking blueprint adds
6 routes: 27 blueprints / 210 route+method.

---

## 2. Non-negotiable boundaries

```text
core and corpus are separate PostgreSQL databases
no cross-database foreign keys
logical IDs only: paper_id / user_id
business reads never hit scipal_rebuild
corpus reads never hit scipal_core
```

Connection factories:

```text
core_connection()          business reads/writes
auth_connection()          auth schema, search_path=auth,public
corpus_connection()        corpus reads
main_read_connection()     corpus reads
owner_connection()         corpus writes (no DDL)
ingest_connection()        corpus ingest writes
```

`pg_connection()` is a compatibility default to the core DSN. New code should
use a named factory.

---

## 3. Retrieval

```text
pgvector HNSW + PostgreSQL GIN FTS + RRF
optional cross-encoder rerank
sentence-level evidence
sentence-window context
```

The stable experiment contract is in `services/search/result.py`:

```text
unit_id
paper_id
hit_sentence_ids       sentences actually scored
context_sentence_ids   context added for generation, never Recall
score
source
```

---

## 4. Security and operations

```text
global API auth       session / bearer / internal token
internal endpoints    /api/ingest, /api/embed require internal token
database roles        core_app / corpus_reader / corpus_writer (no DDL)
environment guard     production rejects loopback/wrong-database DSNs
backups               core 6h/7d; corpus 7d/28d; encrypted
restore drill         data + GIN + HNSW validated 2026-11-12
governance gate       high-risk changes need human approval
```

DDL belongs to migrations, not app startup:

```text
app role has no CREATE
missing plugin schema -> HTTP 503
scripts/migrate_ingest_tracking.py runs with owner DSN
```

---

## 5. Where to look

| Question | Document |
|---|---|
| Routes and request flow | [Architecture and Routes](Architecture-and-Routes.md) |
| Module responsibilities | [Modules and Routes](Modules-and-Routes.md) |
| Data ownership | [数据层隔离审计](../数据层隔离审计.md) |
| Backup strategy | [备份策略-双库](../备份策略-双库.md) |
| Restore drill | [恢复演练-20261112](../恢复演练-20261112.md) |
| Code review findings | [代码审查-20261112](../代码审查-20261112.md) |
| Governance gate | [工程治理门禁规范](../工程治理门禁规范.md) |
| Machine contract | [ARCHITECTURE.json](../../ARCHITECTURE.json) |
