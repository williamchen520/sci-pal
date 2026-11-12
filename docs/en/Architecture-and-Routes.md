# SciPal Architecture and Routes

> **Current state — 2026-11-12**  
> Flask + PostgreSQL 16 + pgvector; `scipal_core` / `scipal_rebuild` are physically separate.  
> 26 blueprints / 204 route+method; 27 / 210 with `SCIPAL_INGEST_TRACKING=1`.

This document covers the current cross-module flow and route groups. The
authoritative endpoint list is `ARCHITECTURE.json`; run
`python scripts/validate_arch.py` after route changes.

---

## 1. Request flow

```text
Browser / DSH / MCP
  -> Caddy (TLS, security headers)
  -> Flask API
     -> auth/session or bearer/internal token
     -> route blueprint
     -> service layer
        -> core_connection()  / corpus_connection()
     -> PostgreSQL
```

Data ownership is enforced at the connection boundary:

```text
business routes  -> scipal_core
corpus routes    -> scipal_rebuild
no cross-database foreign keys
logical paper_id / user_id only
```

---

## 2. Route groups

| Group | Examples | Data layer |
|---|---|---|
| Core / health | `/api/health`, `/api/retrieve` | mixed / health |
| Auth / workspace | `/api/auth/login`, `/api/auth/me`, `/api/workspaces` | core |
| Papers | `/api/papers`, `/api/papers/<id>`, `/api/papers/<id>/trace` | corpus |
| Abstracts | `/api/abstracts/list` | corpus |
| Search | `/api/search/hybrid`, `/api/search/online` | corpus |
| Evidence | `/api/evidence/search`, `/api/evidence/context` | corpus |
| QA | `/api/qa/*` | corpus + LLM |
| Reviews | `/api/reviews`, `/api/review-projects/*` | core |
| Projects / experiments | `/api/projects`, `/api/experiments`, `/api/runs` | core |
| Claims | `/api/claims/*` | core |
| Protocols / references | `/api/protocols`, `/api/references` | core |
| Watch | `/api/watch/*` | core |
| Tasks | `/api/tasks` | core |
| Ingest | `/api/ingest`, `/api/embed` | corpus (internal token) |
| Ingest tracking | `/api/ingest-tracking/*` | core (optional plugin) |

`/api/ingest` and `/api/embed` require:

```text
X-SCIPAL-Internal-Token: <SCIPAL_INTERNAL_TOKEN>
```

They are not public endpoints.

---

## 3. Auth model

```text
public:        /api/health, /api/auth/login
session:       browser login
bearer:        SCIPAL_API_TOKEN (optional)
internal:      service token + configured service user/workspace
```

The internal token is bound to:

```text
SCIPAL_INTERNAL_USER_ID
SCIPAL_INTERNAL_WORKSPACE_ID
```

It is not a browser cookie and must not be exposed to the frontend.

---

## 4. Data flow: paper trace

```text
GET /api/papers/<paper_id>/trace?sentence_id=...
  -> auth
  -> PaperStore.in_workspace()       corpus read
  -> sentences / papers / sections   corpus read
  -> signed PDF/image URLs
```

The earlier bug here was a core connection querying corpus tables; it returned
HTTP 500 with `relation "papers" does not exist`. `PaperStore` now uses
`main_read_connection()` for reads and `owner_connection()` for writes.

---

## 5. Data flow: evidence search

```text
POST /api/evidence/search
  -> SentenceHybridRetriever
     -> pgvector HNSW (corpus)
     -> sentence FTS (corpus)
     -> RRF
     -> sentence window
  -> evidence envelope
```

The stable experiment contract is:

```text
RetrievalHit:
  unit_id
  paper_id
  hit_sentence_ids
  context_sentence_ids
  score
  source
```

`context_sentence_ids` must never be counted as Recall.

---

## 6. Operational endpoints

```text
/app health        /api/health
pg-backup          encrypted dumps, restore drill
watch-cron         monitoring scheduler
governance gate    scripts/governance_gate.py (not an HTTP route)
```

Production DSNs are validated by `services/db/env_guard.py` when
`SCIPAL_ENV=production`.

---

## 7. Route change rules

Before adding or changing a route:

1. update `ARCHITECTURE.json`;
2. run `python scripts/validate_arch.py`;
3. add a route/service test;
4. if the change touches API/DB/DSN contracts, stop for human approval.

```text
wild routes are rejected
planned routes are allowed only with status=planned
optional plugin routes use feature_flag + optional
```

---

## 8. Related documents

- [Architecture Overview](Architecture-Overview.md)
- [Modules and Routes](Modules-and-Routes.md)
- [ARCHITECTURE.json](../../ARCHITECTURE.json)
- [Data isolation audit](../数据层隔离审计.md)
- [Backup strategy](../备份策略-双库.md)
- [Governance gate](../工程治理门禁规范.md)
- [Current code review](../代码审查-20261112.md)
