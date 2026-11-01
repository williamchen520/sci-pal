# SciPal Architecture and Routes

> Version: V33.96+ (2026-10-31)  
> Code: Flask + SQLite + ChromaDB + vanilla HTML/JS  
> Deployment: Docker Compose (app + watch-cron + Caddy)
>
> ⚠️ The project is under heavy development (WIP) and must not be used in production. See the README in the repository root for details.

---

## 1. Design Principles

```text
deterministic retrieval
  ↓
structured evidence
  ↓
claim interrogation
  ↓
constrained writing
```

Three ground rules:

1. **Retrieval is traceable**: every paragraph, sentence, figure, and table can be traced back to paper_id / section / page / bbox.
2. **Claims have evidence**: a claim must be bound to an exact quote; no assertion without evidence.
3. **Adjudication is auditable**: state changes are written to an event table; history is never overwritten.

---

## 2. System Layers

```mermaid
%%{init: {"flowchart": {"curve": "basis"}}}%%
flowchart TB
  subgraph C["Clients"]
    DSH["DSH / MCP"]
    WEB["Browser<br/>index / projects / reviews / watch / packs / claims"]
  end

  subgraph API["Flask API"]
    R1["auth / tenancy"]
    R2["papers / search / qa"]
    R3["reviews / review_actions"]
    R4["watch / domain-packs / claims"]
    R5["projects / experiments / runs"]
    R6["ingest / tasks / guard / protocols"]
  end

  subgraph SVC["services/*"]
    S1["search<br/>hybrid · rerank · context"]
    S2["qa · review · quality"]
    S3["watch<br/>profiles · runs · digest · scheduler"]
    S4["domain_packs<br/>loader · validator"]
    S5["claims<br/>retrieval · semantic · nli · service"]
    S6["tenancy · projects · experiments"]
    S7["security · trust · protocols"]
  end

  subgraph BDB["build_db/*"]
    B1["parsers / import_jats / structure"]
    B2["watch_schema / claim_pilot_schema"]
    B3["sentence_geometry / links"]
  end

  subgraph D["Storage"]
    DB[("SQLite research.db")]
    CH[("ChromaDB")]
    FS["documents / documents_xml / packs"]
  end

  subgraph X["External"]
    EPMC["Europe PMC / PMC"]
    OA["OpenAlex / Crossref"]
    LLM["DeepSeek / Ollama"]
  end

  DSH --> API
  WEB --> API
  API --> SVC
  SVC --> BDB
  BDB --> DB
  SVC --> DB
  SVC --> CH
  BDB --> FS
  SVC --> X
```

Current scale:

```text
26 registered blueprints
~180 routes
9 frontend pages
735 tests
```

---

## 3. Data Layers

### L0: document tree

```text
papers
 └─ sections
     └─ paragraphs
         ├─ sentences
         ├─ figures
         └─ tables
```

Key fields:

```text
paper_id / section_id / para_id / sentence_id
page / bbox / char_start / char_end
section_path / depth / parent_id
```

### L1: evidence units

- `sentences`: sentence-level text + offsets;
- `figures` / `tables`: caption + markdown;
- `sentence_links`: sentence ↔ citation/figure/table;
- `paper_links`: cites / cited_by / similar.

### L2: claims

```text
claim_cards
claim_card_evidence
claim_card_events
```

`claim_cards`:

```text
claim_id
workspace_id
title / claim_text / claim_type
status
qualifiers_json
corpus_json
warrant / backing / rebuttal / strongest_counter
writing_brief
decision / decision_note / decided_by / decided_at
```

`claim_card_evidence`:

```text
claim_id
paper_id / node_type / node_id
relation: supports | refutes | mentions | underdetermines
strength / quote / rationale
```

### L3: watch

```text
watch_profiles
watch_profile_journals
watch_runs
watch_items
watch_seen
```

### L4: multi-user / projects

```text
users / workspaces / memberships / tenancy_audit
projects / project_members
experiments / experiment_runs / experiment_revisions
experiment_signatures / experiment_access_requests
```

---

## 4. Retrieval Flow

```mermaid
sequenceDiagram
  participant U as DSH/Browser
  participant API as Flask
  participant HS as HybridSearch
  participant CH as Chroma
  participant FTS as SQLite FTS5
  participant RR as Reranker
  participant CE as ContextExpander
  participant DB as SQLite

  U->>API: query
  API->>HS: search()
  HS->>CH: vector recall of paragraphs
  HS->>FTS: BM25 recall
  HS->>HS: RRF + MMR
  HS->>RR: cross-encoder rerank
  RR-->>HS: top-k
  HS->>CE: paragraph → whole section / neighboring paragraphs / sentences
  CE->>DB: section_path + sentences + links
  CE-->>API: evidence envelope
  API-->>U: citations + evidence
```

Key fix:

```text
Chroma $in must receive a list, not a set
→ chroma_paper_filter()
```

---

## 5. Claim Interrogation Flow

```text
topic / papers
  ↓
claim extraction / manual entry
  ↓
qualifiers
  ↓
supporting / opposing / boundary retrieval
  ↓
NLI: supports / refutes / mentions / underdetermines
  ↓
human adjudication
  ↓
writing_brief
  ↓
writing gate
```

State machine:

```text
draft
  ↓
interrogating
  ↓
supported / contested / underdetermined
  ↓
accepted / revised / contested / rejected
```

Current status distribution:

```text
accepted: 3
revised: 3
contested: 2
underdetermined: 2
```

Key claims:

```text
claim_hcc_triple_os
accepted → contested
refutes: LEAP-012 / EMERALD-1 OS not mature
writing_brief: PFS is writable; significant OS benefit is not
```

---

## 6. Watch Flow

```text
profile
  ↓
discover journals / Crossref
  ↓
window search
  ↓
dedup
  ↓
score: profile match + journal metric + recency
  ↓
select: max_items + same_journal_limit
  ↓
ingest abstract / fulltext
  ↓
digest
  ↓
feedback: useful / not_useful
```

Scheduling:

```text
services/watch/scheduler.py
scripts/run_watch_due.py
docker compose service: watch-cron
check next_run_at every 5 minutes
```

---

## 7. Domain Packs

```text
packs/biomed-oncoimmuno/
├─ pack.yaml
├─ taxonomy.yaml
├─ section_types.yaml
├─ evidence_schema.yaml
├─ sources.yaml
├─ prompts/
├─ eval/claims_pilot.yaml
├─ eval/claim_counterexamples.yaml
└─ README.md
```

Loading:

```text
services/domain_packs/loader.py
GET /api/domain-packs
GET /api/domain-packs/<id>
GET /api/domain-packs/<id>/validate
```

Principles:

- the core does not import concrete domain packs;
- declarative first;
- Python hooks come later;
- unsigned/unvalidated packs do not reach production.

---

## 8. Deployment Topology

```mermaid
flowchart LR
  U["Browser"] --> Caddy["Caddy :80/:443"]
  Caddy --> App["app :5000"]
  App --> Data[("data/research.db + chroma")]
  App --> Models[("models/ (ro)")]
  Cron["watch-cron"] --> Data
  App --> LLM["DeepSeek / Ollama"]
```

Services:

```text
app         Flask + Gunicorn/dev server
watch-cron  dispatch of due profiles
caddy       reverse proxy
```

Data paths:

```text
G:\sciPal_deploy\
├─ data/
├─ documents/
├─ documents_xml/
├─ models/
└─ logs/
```

---

## 9. Authentication and Isolation

```text
session user_id
  ↓
workspace_id
  ↓
role: owner | pi | member | viewer
  ↓
authorize()
```

Isolation points:

- papers / notes / favorites / projects / experiments;
- retrieval: `allowed_paper_ids()` → `filters["paper_ids"]`;
- QA: a paper_id from another workspace → 404;
- watch: owner-level isolation;
- PI: read-only/copy, cannot modify another user's experiments; experiments require owner approval.

`SCIPAL_AUTH_REQUIRED` is off by default, for compatibility with single-user local use.

---

## 10. Route Groups

| Group | Prefix |
|---|---|
| Auth / workspaces | `/api/auth/*` `/api/workspaces/*` |
| Retrieval | `/api/retrieve` `/api/search/*` |
| Papers | `/api/papers/*` |
| Q&A | `/api/qa/*` `/api/agentic/*` |
| Reviews | `/api/review/*` `/api/reviews/*` |
| Watch | `/api/watch/*` |
| Domain packs | `/api/domain-packs/*` |
| Claims | `/api/claims/*` |
| Projects / experiments | `/api/projects/*` `/api/experiments/*` `/api/runs/*` |
| Ingest / tasks | `/api/ingest/*` `/api/tasks/*` |
| Quality / protocols | `/api/guard/*` `/api/protocols/*` |

`routes/` and `api_server.py` are the authoritative source for the complete route list.

---

## 11. Frontend Pages

| Page | Purpose |
|---|---|
| `index.html` | Home |
| `login.html` | Sign-in |
| `projects.html` | Projects / experiments / runs / audit / signatures |
| `reviews.html` | Review outline / generation / history |
| `watch.html` | Watch profiles / weekly digest / feedback |
| `packs.html` | Domain pack inspection / validation |
| `claims.html` | Claim cards / evidence / decisions / writing stance |
| `trace.html` | Sentence tracing |
| `compare.html` | Two-column comparison |
| `viewer.html` | PDF reading |

---

## 12. Tests and Boundaries

```text
735 tests
~60s
```

Coverage:

- retrieval / routes / guard;
- JATS import / sentences;
- watch / scheduler / feedback;
- domain packs;
- claim card / evidence / decision / writing brief;
- multi-user isolation / projects / experiments / runs.

### Stop-loss guard

```text
services/quality/stop_loss.py
scripts/run_tests_guarded.py
scripts/record_eval_metric.py
logs/stop_loss_state.json
```

Rules:

- the same test fails twice in a row → exit code 2;
- the same metric fails to improve twice in a row → exit code 2;
- output: `触发止损规则，停止调参，等待人类介入`.

### Plugin ports (M0/M1)

```text
plugins/manifests/*.yaml   identity / version / entrypoint / license
plugins/ports/*.json       core-owned input/output schema
plugins/adapters/*.py      adapter.run(payload) -> dict
services/plugins/          contracts / registry / runner / claim_contracts
eval/plugin_bench.py       general comparison entry point
eval/claim_verifier_bench.py  ClaimVerifier comparison
logs/plugin_runs.jsonl     provenance of every call
```

M1 integrated:

```text
claim-verifier-nli
claim-verifier-rule
claim-verifier-underdetermines
```

First-round results:

```text
10 claims / 11 evidence
rule accuracy 0.3636
underdetermines 0.0000
majority baseline 0.9091
```

Conclusion: the pipeline passes, but the data is severely imbalanced, so it cannot be used to judge the merits of the algorithms.

Balanced dataset (derived):

```text
eval/plugins/claims_pilot_balanced_cases.json
30 cases = 10 supports / 10 refutes / 10 underdetermines
```

```text
rule accuracy          0.4333
underdetermines        0.3333
majority baseline      0.3333
```

Refutes are derived from "explicitly negated claim + the same supporting evidence" and need manual review before release.

M2 integrated:

```text
retriever-bm25
retriever-dense
retriever-hybrid
retriever-hybrid-rerank
```

Hybrid results (74 queries / 100 papers):

```text
bm25        Recall@10 0.9459  MRR 0.8149
dense       Recall@10 0.9324  MRR 0.8829
hybrid      Recall@10 0.9459  MRR 0.9036
hybrid+rr   Recall@10 0.9865  MRR 0.9081
```

Midway through, we found that the hybrid adapter read paper_id from the top level while it actually lives in metadata;
after the fix, hybrid recovered from 0.7778, and we added a regression test.

The query set contains 20 cross-topic queries plus 48 distractors, but it is still not a publication-grade benchmark.

### Benchmark DB policy

```text
default: postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
>100 papers or concurrent: SQLite prohibited
small-scale SQLite: SCIPAL_BENCH_ALLOW_SQLITE=1 required
```

Implementation:

```text
services/quality/benchmark_db.py
tests/test_benchmark_db.py
```

The PostgreSQL business backend is not implemented yet; the policy is fail-fast.

### PostgreSQL migration (planned)

```text
P0 backup/baseline
P1 schema + DBAdapter
P2 read-only ETL
P3 shadow reads
P4 dual writes
P5 cutover
P6 archive
```

Safety red lines:

```text
the original data/research.db is read-only and must not be overwritten by migration scripts;
migration uses snapshots only;
backup_sqlite.py + integrity_check are required before every migration.
```

Docs:

```text
docs/工作计划-PostgreSQL迁移.md
docs/PostgreSQL迁移-基线.md
scripts/backup_sqlite.py
```

P1 implemented (pending merge):

```text
build_db/postgres_schema.sql
build_db/generate_postgres_schema.py
services/db/adapter.py
tests/test_db_adapter.py
```

Constraints:

```text
default SCIPAL_DB_BACKEND=sqlite
PostgreSQL requires SCIPAL_PG_DSN + psycopg
no data migration
no read-path cutover
connection pooling deferred to P2
```

P2 implemented (pending merge):

```text
services/db/etl.py
scripts/pg_etl.py
tests/test_pg_etl.py
```

Real COPY (local PostgreSQL 16):

```text
60 tables
expected 2,015,676 / postgres 2,015,676
count mismatch 0
papers/paragraphs/sentences diff 0
citations year TEXT coercion; non-year fields diff 0
```

Safety:

```text
read-only snapshot
rejects data/research.db
no write-back to SQLite
```

P3 implemented (pending merge):

```text
services/db/shadow_read.py
scripts/shadow_read.py
tests/test_shadow_read.py
```

Results:

```text
8 core tables, full key comparison: 0 missing / 0 extra / 0 field diff
FTS: match sets differ (Jaccard 0.326–0.828)
cause: SQLite unicode61 has no stemming / PG english does
ranking: bm25 vs ts_rank_cd
conclusion: the data layer can proceed; FTS cannot be switched directly
```

FTS alignment experiment:

```text
unicode61 vs english: Jaccard 0.326–0.828
porter    vs english: Jaccard 0.986–0.992
```

20 queries at paper level:

```text
unicode61 Recall@10 1.000
porter    Recall@10 0.950
PG english Recall@10 0.600
```

Conclusion: porter improves the match set but does not improve retrieval; FTS is not switched for now.

P4 metadata dual writes (installed):

```text
services/db/dual_write.py
scripts/setup_dual_write.py
scripts/replay_dual_write.py
21 tables / 63 triggers
dual_write_outbox
FTS is not dual-written
SQLite is still the primary database
staging soak: 2,422 ops / 0 failed / 0 mismatch
```

P5 read canary (pending merge):

```text
GET /api/papers list
SCIPAL_READ_CANARY_PERCENT=0..100
automatic fallback to SQLite on PG errors
X-SciPal-Read-Backend response header
3,310 rows / same_order true / field_diffs 0
```

Current limitations:

1. The claim pilot covers only 10 HCC claims; it is not general claim extraction.
2. Counterexample retrieval is still limited by the local corpus; the online import completed only 2 papers.
3. The writing gate is still brief + manual check, not automatic rejection of generation.
4. SQLite is single-node; multi-user scale is limited.
5. Moving private data to the cloud requires additional routing/compliance controls.
