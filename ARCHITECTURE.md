# SciPal Architecture

> **Last updated:** 2026-11-08 · PG-only  
> **Canonical machine-readable spec:** [ARCHITECTURE.json](ARCHITECTURE.json)  
> **Detailed diagrams and routes:** [docs/架构与路由图.md](docs/架构与路由图.md)

This file is a short entry point. The previous long-form architecture document described the retired SQLite + Chroma stack and is no longer authoritative.

---

## Current stack

```text
Python 3.12
Flask 3
PostgreSQL 16 + pgvector
PostgreSQL FTS (GIN tsvector; optional ParadeDB)
Vanilla HTML/CSS/JS + PDF.js
Docker Compose: app + watch-cron + Caddy + PostgreSQL
```

Retired:

```text
SQLite research.db   archived, not mounted, not created
Chroma               archived, not initialized
```

---

## Runtime shape

```text
Browser / DSH
    -> Flask API (26 blueprints, 186 routes)
       -> services/search, review, claims, projects, watch, ...
       -> build_db/* parsing and writes
    -> PostgreSQL + pgvector
    -> documents/ + packs/
```

---

## Non-negotiable rules

1. Retrieval is deterministic and traceable to paper / section / paragraph / sentence / page / bbox.
2. Claims bind to explicit quotes.
3. State changes are append-only audit events.
4. PostgreSQL is the only production store; do not reintroduce SQLite or Chroma into runtime paths.
5. External capabilities are plugins and must be removable without changing the core.

---

## Where to look

| Question | Document |
|---|---|
| Data flow, routing, storage | [docs/架构与路由图.md](docs/架构与路由图.md) |
| Module responsibilities and entry points | [docs/开发-模块手册.md](docs/开发-模块手册.md) |
| Migration decisions and verification | [docs/PG-only迁移总报告-2026-11-08.md](docs/PG-only迁移总报告-2026-11-08.md) |
| Machine-readable architecture | [ARCHITECTURE.json](ARCHITECTURE.json) |
