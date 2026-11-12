# SciPal Architecture

> **Last updated:** 2026-11-12 · PG-only, physically separated core/corpus  
> **Canonical machine-readable spec:** [ARCHITECTURE.json](ARCHITECTURE.json)  
> **Chinese route map:** [docs/架构与路由全景图.md](docs/架构与路由全景图.md)  
> **English route map:** [docs/en/Architecture-and-Routes.md](docs/en/Architecture-and-Routes.md)

This is the short architecture entry point. Detailed migration history lives in
`docs/`; this file describes the current runtime.

---

## Current stack

```text
Python 3.12
Flask 3
PostgreSQL 16 + pgvector
PostgreSQL FTS (GIN tsvector; optional ParadeDB)
Vanilla HTML/CSS/JS + PDF.js
Docker Compose: app + pg-backup + watch-cron + Caddy + PostgreSQL
Caddy: HTTPS, security headers
```

Retired:

```text
SQLite research.db   archived, not mounted, not created
Chroma               archived, not initialized
```

---

## Runtime shape

```text
Browser / DSH / MCP
    -> Caddy (TLS, security headers)
    -> Flask API
       -> scipal_core
       -> scipal_rebuild
       -> services/search, review, claims, projects, watch, ...
       -> build_db/* parsing and corpus writes
    -> documents/ + packs/
```

Route count:

```text
26 blueprints / 204 route+method by default
27 blueprints / 210 route+method with SCIPAL_INGEST_TRACKING=1
```

---

## Two-database contract

```text
scipal_core
  users / auth / workspaces / memberships
  projects / experiments / notes / tasks
  claims / reviews / audit

scipal_rebuild
  papers / sections / paragraphs / sentences
  paragraph_embeddings / citations / figures / tables
```

Rules:

```text
no cross-database foreign keys
logical IDs only (paper_id / user_id)
core connections never query corpus tables
corpus connections never query business tables
business reads do not hit scipal_rebuild
corpus reads do not hit scipal_core
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

`pg_connection()` remains only as a compatibility default to the core DSN.

---

## Security model

```text
global API auth         session / bearer / internal token
internal endpoints      /api/ingest, /api/embed require X-SCIPAL-Internal-Token
database roles          core_app / corpus_reader / corpus_writer
                        no DDL for the application role
environment guard       production rejects loopback and wrong-database DSNs
secrets                 environment only; never commit real credentials
```

DDL is a migration/owner responsibility:

```text
app startup must not CREATE/ALTER tables
missing plugin schema returns 503
migration script: scripts/migrate_ingest_tracking.py
```

---

## Backup and recovery

```text
core      every 6h, retain 7d
corpus    every 7d, retain 28d
format    pg_dump custom + AES-256-CBC/PBKDF2
verify    pg_restore --list before encryption
restore   data + GIN + HNSW validated 2026-11-12
```

Do not claim a backup is valid until a restore drill has passed.

---

## Non-negotiable rules

1. Retrieval is deterministic and traceable to paper / section / paragraph / sentence / page / bbox.
2. Claims bind to explicit quotes.
3. State changes are append-only audit events.
4. PostgreSQL is the only production store; do not reintroduce SQLite or Chroma into runtime paths.
5. External capabilities are plugins and must be removable without changing the core.
6. High-risk changes pass the governance gate and human approval.

---

## Where to look

| Question | Document |
|---|---|
| Data flow, routing, storage | [docs/en/Architecture-and-Routes.md](docs/en/Architecture-and-Routes.md) |
| Chinese route map | [docs/架构与路由全景图.md](docs/架构与路由全景图.md) |
| Module responsibilities | [docs/en/Modules-and-Routes.md](docs/en/Modules-and-Routes.md) |
| Data ownership | [docs/数据层隔离审计.md](docs/数据层隔离审计.md) |
| Backup/restore | [docs/备份策略-双库.md](docs/备份策略-双库.md) |
| Restore drill | [docs/恢复演练-20261112.md](docs/恢复演练-20261112.md) |
| Code review findings | [docs/代码审查-20261112.md](docs/代码审查-20261112.md) |
| Governance gate | [docs/工程治理门禁规范.md](docs/工程治理门禁规范.md) |
| Machine-readable architecture | [ARCHITECTURE.json](ARCHITECTURE.json) |
