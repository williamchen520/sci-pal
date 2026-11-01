# Work Plan: SQLite → PostgreSQL Migration

> Date: 2026-10-31  
> Status: Plan; no migration implementation included  
> Prerequisite policy: [Benchmark PostgreSQL Strategy](../../benchmark-PostgreSQL策略.md)  
> Overriding principle: **The original SQLite data is read-only and must never be overwritten by the migration; every phase must be reversible.**

---

## 1. Background

SciPal started as a single-user, single-machine tool backed by SQLite:

```text
data/research.db
data/chroma/
```

It now supports multiple users, projects, experiments, watches, claims, and plugin benchmarks, and SQLite's limits are clear:

```text
Limited write concurrency
Long transactions block
FTS5 and PostgreSQL use different syntax
Unreliable with multiple workers
```

The goal is not to "swap the connection string" but to:

```text
Migrate metadata and full-text search to PostgreSQL in phases,
without losing existing data,
while keeping a verifiable rollback path.
```

---

## 2. Non-Goals

```text
Do not migrate Chroma in this phase (the vector store stays separate)
No cross-datacenter deployment or sharding
No PostgreSQL RLS (later)
Do not delete the original SQLite files
No big-bang cutover
```

---

## 3. Hard Data-Safety Rules

### 3.1 Original Database Is Read-Only

During migration, no script may:

```text
Run INSERT / UPDATE / DELETE / VACUUM / DROP against data/research.db
Use data/research.db as a migration target
Overwrite data/research.db
```

Migration operates only on a copy:

```text
data/migration/research_snapshot.db
```

### 3.2 Back Up First, Then Migrate

Before every migration step, you must:

```text
1. Generate a consistent snapshot with VACUUM INTO
2. Copy it to backups/
3. Run PRAGMA integrity_check
4. Record per-table row counts and the SHA-256
5. Keep a second copy on the G: drive
```

Example:

```powershell
python scripts\backup_sqlite.py
```

What the script does:

```text
1. Open the source database read-only (mode=ro)
2. Generate a consistent snapshot with VACUUM INTO
3. Run PRAGMA integrity_check on the snapshot
4. Count rows in papers
5. Compute the SHA-256
6. Refuse to overwrite an existing snapshot
```

Sample output:

```json
{
  "source": "data/research.db",
  "dest": "backups/research_20261031_210616.db",
  "bytes": 1769127936,
  "source_integrity": "ok",
  "backup_integrity": "ok",
  "papers": 3310,
  "sha256": "..."
}
```

Then copy the snapshot to the second drive:

```powershell
Copy-Item "D:\sciPal\backups\research_20261031_210616.db" `
  "G:\sciPal_deploy\backups\research_20261031_210616.db"
(Get-FileHash "G:\sciPal_deploy\backups\research_20261031_210616.db" -Algorithm SHA256).Hash
```

### 3.3 Backup Retention

```text
Local backups/: at least 30 days
G:\sciPal_deploy\backups\: at least 30 days
One extra copy before every schema change
```

### 3.4 Rollback Rules

```text
If any phase fails: stop, do not write back to SQLite, and switch straight back to the original database.
The original SQLite database stays startable for the entire migration.
Mark it as a read-only archive only after P6 acceptance passes.
```

---

## 4. Current-State Audit

### 4.1 Scale

```text
SQLite call sites: about 600
Tables: about 70 (including FTS shadow tables)
Core large tables:
  papers       ~3,300
  paragraphs   ~167,000
  sentences    ~862,000
  citations    ~182,000
  sentence_links ~296,000
  paper_links  ~164,000
```

### 4.2 Main Modules

```text
services/search/         FTS5 + Chroma + RRF
services/claims/         claim_cards / evidence / events
services/watch/          profiles / runs / items
services/projects/       projects / members
services/experiments/    experiments / runs / revisions
services/review/         review projects / screening / risk of bias
services/notes/          notes
services/tenancy/        users / workspaces / memberships
routes/*                 direct SQL in the API layer
build_db/*               import / schema rebuild
eval/*                   benchmark reads
```

### 4.3 SQLite-Specific Dependencies

| Dependency | Migration action |
|---|---|
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` |
| `AUTOINCREMENT` | `GENERATED ... AS IDENTITY` |
| `?` placeholders | `%s` |
| `PRAGMA table_info` | `information_schema.columns` |
| `sqlite3.Row` | `psycopg.rows.dict_row` |
| `json_extract` | `jsonb ->` / `->>` |
| FTS5 `MATCH` / `bm25()` | `tsvector` + `websearch_to_tsquery` + `ts_rank_cd` |
| `VACUUM INTO` | `pg_dump` snapshots |
| `sqlite3.Connection.backup` | No longer used |

---

## 5. Target Architecture

```text
Flask / services
  ↓
DBAdapter (new)
  ├─ SQLiteAdapter (existing, retained)
  └─ PostgresAdapter (new)
        ↓
   PostgreSQL
     ├─ metadata tables
     ├─ full-text search (tsvector + GIN)
     └─ audit / tasks
```

Configuration:

```text
SCIPAL_DB_BACKEND=sqlite | postgres
SCIPAL_PG_DSN=postgresql://...
SCIPAL_PG_POOL_MIN=1
SCIPAL_PG_POOL_MAX=10
```

Principles:

```text
Business code does not depend on psycopg directly
Connections, transactions, and row factories all come from DBAdapter
The SQLite path stays available until P6
```

---

## 6. Schema Mapping

### 6.1 Core Tables

| SQLite | PostgreSQL |
|---|---|
| `papers` | `papers` |
| `sections` | `sections` |
| `paragraphs` | `paragraphs` |
| `sentences` | `sentences` |
| `figures` / `tables` | `figures` / `tables` |
| `citations` | `citations` |
| `sentence_links` | `sentence_links` |
| `paper_links` | `paper_links` |
| `claim_cards` | `claim_cards` |
| `claim_card_evidence` | `claim_card_evidence` |
| `claim_card_events` | `claim_card_events` |
| `watch_*` | `watch_*` |
| `users` / `workspaces` / `memberships` | Same names |
| `projects` / `experiments` / `experiment_runs` | Same names |

### 6.2 Types

```text
TEXT       -> text
INTEGER    -> integer / bigint
REAL       -> double precision
JSON strings -> jsonb (optional; keep as text initially)
Time strings -> timestamptz (parsed during migration)
```

### 6.3 Full-Text Search

SQLite:

```sql
SELECT ... FROM paragraphs_fts WHERE paragraphs_fts MATCH ? ORDER BY bm25(paragraphs_fts)
```

PostgreSQL:

```sql
ALTER TABLE paragraphs ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED;

CREATE INDEX paragraphs_search_idx ON paragraphs USING GIN (search_vector);

SELECT ... FROM paragraphs
WHERE search_vector @@ websearch_to_tsquery('english', %s)
ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) DESC;
```

Must be replaced:

```text
papers_fts
paragraphs_fts
sentences_fts
summaries_fts
```

Chinese content needs a separate approach:

```text
Keep the original text for now; use pg_trgm or external segmentation for Chinese search
Not addressed in P1
```

---

## 7. Phased Implementation

### P0: Freeze and Back Up

```text
1. Record the current version, git commit, and DB row counts
2. Take a VACUUM INTO snapshot
3. Back up to both drives
4. Run integrity_check
5. Open the snapshot read-only and run a sample query
```

Acceptance:

```text
Backup opens
Row counts match
Core query results match
Original database unmodified
```

### P1: Schema and Connection Layer

```text
1. Write the PostgreSQL schema DDL
2. Write DBAdapter (connections/transactions/row factories)
3. Keep SQLite as the default; do not switch
4. Write unit tests for the adapter
```

P1 implementation (pending merge):

```text
build_db/postgres_schema.sql
build_db/generate_postgres_schema.py
services/db/adapter.py
services/db/__init__.py
tests/test_db_adapter.py
```

Constraints:

```text
Default is SCIPAL_DB_BACKEND=sqlite
PostgreSQL requires SCIPAL_PG_DSN + psycopg
No data migration in this phase
No read-path switch in this phase
Connection pooling is deferred to P2
```

Acceptance:

```text
All 699+ tests on the SQLite path still pass
PostgreSQL schema can be generated
Adapter can connect/commit/roll back/close
Schema includes the core tables plus tsvector/GIN
```

### P2: Read-Only ETL

```text
1. Read data from the snapshot
2. Bulk-load into PostgreSQL with COPY
3. Record per-table row counts and checksums
4. Never write back to SQLite
```

Acceptance:

```text
Row counts match
Sampled primary/foreign keys match
Core search query results are comparable
```

P2 implementation (pending merge):

```text
services/db/etl.py
scripts/pg_etl.py
tests/test_pg_etl.py
docs/PostgreSQL迁移-ETL-dryrun.json
docs/PostgreSQL迁移-ETL-checksum.json
docs/PostgreSQL迁移-ETL-verify.json
docs/PostgreSQL迁移-ETL-execute-citations.json
```

Safety:

```text
assert_snapshot rejects data/research.db
Snapshot opened read-only
No write-back to SQLite
```

Results (local PostgreSQL 16):

```text
60 tables
expected_rows = 2,015,676
postgres_rows = 2,015,676
count_mismatches = 0
```

Row-by-row comparison of core tables:

```text
papers       0 missing / 0 extra / 0 diff
paragraphs   0 missing / 0 extra / 0 diff
sentences    0 missing / 0 extra / 0 diff
citations    0 missing / 0 extra; year converted to TEXT, 0 diffs in non-year fields
```

Found and fixed:

```text
citations.year contains free text such as 'Feb 3, 2020';
the PostgreSQL schema now uses TEXT to avoid bigint conversion failures.
```

The real COPY has run; the source database is still the read-only snapshot.

### P3: Shadow Reads

```text
1. SCIPAL_READ_FROM_PG=0/1 switch
2. Run the same query against both SQLite and PG
3. Compare top-k, counts, and key fields
4. Record differences only; do not change the production read path
```

Acceptance:

```text
Difference rate within an explainable range
Documented list of FTS result differences
```

P3 implementation (pending merge):

```text
services/db/shadow_read.py
scripts/shadow_read.py
tests/test_shadow_read.py
docs/PostgreSQL迁移-P3-shadow.json
```

Results (local PostgreSQL 16):

```text
Full key comparison on 8 core tables: 0 missing / 0 extra / 0 field diffs
papers        3,310
paragraphs  167,388
sentences   862,677
claim_cards      10
claim_card_evidence 17
watch_items      11
users              1
workspaces         1
```

FTS shadow reads:

| query | SQLite matches | PG matches | match Jaccard | top-10 common |
|---|---:|---:|---:|---:|
| hepatocellular carcinoma | 1,023 | 785 | 0.757 | 0 |
| immune checkpoint inhibitor | 321 | 786 | 0.326 | 1 |
| tumor microenvironment | 2,813 | 2,611 | 0.828 | 2 |

Conclusion:

```text
Table data is identical.
The FTS gap is not data loss but tokenizer/stemmer differences:
  SQLite unicode61 (no stemming)
  PostgreSQL english (with stemming)
```

Ranking differs too:

```text
SQLite ranks by bm25
PostgreSQL ranks by ts_rank_cd
```

So the P3 conclusion is:

```text
The data layer can proceed to P4;
FTS cannot be switched directly; first unify the tokenizer/stemmer, or accept the ranking differences after review.
```

FTS alignment experiment:

```text
scripts/fts_alignment.py
docs/PostgreSQL迁移-FTS对齐实验.md
docs/PostgreSQL迁移-FTS对齐实验.json
```

Results:

```text
unicode61 vs english: mean match Jaccard 0.637
porter    vs english: mean match Jaccard 0.989
```

Conclusion:

```text
porter + english are the closest match;
but a 20-query paper-level test shows porter does not improve retrieval:
  unicode61 Recall@10 1.000
  porter    Recall@10 0.950
  PG english Recall@10 0.600
```

Therefore:

```text
FTS is not switched for now.
P4 dual-writes metadata tables only; FTS continues to use SQLite unicode61.
```

Porter rebuild and the 20 queries:

```text
scripts/rebuild_fts_porter.py
scripts/fts_porter_compare.py
docs/PostgreSQL迁移-FTS-porter-20query.md
docs/PostgreSQL迁移-FTS-porter-20query.json
docs/PostgreSQL迁移-FTS-porter-rebuild.json
```

### P4: Dual Writes

```text
1. SQLite remains primary
2. After a successful SQLite write, write to PostgreSQL asynchronously
3. Failures go to a replay queue
4. Record lag
```

Acceptance:

```text
Staging soak covers inserts/updates/deletes
Replay catches up
Rollback only requires stopping dual writes; SQLite remains complete
```

P4 implementation (pending merge):

```text
services/db/dual_write.py
scripts/setup_dual_write.py
scripts/replay_dual_write.py
scripts/p4_staging_soak.py
tests/test_dual_write.py
docs/PostgreSQL迁移-P4-dualwrite-setup.json
docs/PostgreSQL迁移-P4-soak.json
```

Mechanism:

```text
SQLite remains the primary database
AFTER INSERT/UPDATE/DELETE triggers installed on 21 metadata tables
Triggers only write to dual_write_outbox and do not block business operations
A replay worker reads the outbox and upserts/deletes into PG
FTS tables get no triggers and are not dual-written
```

Current status:

```text
Installed: 21 tables / 63 triggers
backup: data/backups/research_20261101_012330.db
outbox pending: 0
Real PG upsert replay: 1 succeeded, 0 failed
staging soak: 2,422 ops / 0 failed / 0 mismatches
```

Acceptance:

```text
[x] SQLite primary unchanged
[x] Writes only append to the outbox
[x] Replay catches up
[x] FTS is outside the dual-write scope
[x] Staging soak passes (500 cycles / 2,422 ops)
[ ] Long-running observation under real production traffic (optional; no longer waiting a 24h wall clock)
```

### P5: Cutover

```text
1. Brief write freeze
2. Confirm PG lag=0
3. SCIPAL_DB_BACKEND=postgres
4. Observe for 24–72h
5. Keep SQLite read-only
```

Rollback:

```text
SCIPAL_DB_BACKEND=sqlite
Stop PG writes
Catch SQLite up with P4's replay/reverse export
```

Acceptance:

```text
Read path works
Write path works
Concurrency tests pass
Rollback drill succeeds
```

P5 canary implementation (pending merge):

```text
services/db/read_router.py
scripts/read_canary_check.py
tests/test_read_router.py
docs/PostgreSQL迁移-P5-canary-check.json
```

Scope:

```text
Switch only list reads for GET /api/papers
Paper detail / graph still use SQLite
Write path unchanged
FTS unchanged
```

Configuration:

```text
SCIPAL_READ_CANARY_PERCENT=0..100
SCIPAL_PG_DSN=...
```

Results:

```text
SQLite count 3,310
PG count 3,310
same_order true
field_diffs 0
missing/extra 0
status ok
```

Rollback:

```text
SCIPAL_READ_CANARY_PERCENT=0
```

### P6: Archival

```text
1. 30 consecutive days without rollback
2. Mark SQLite as archive; no further writes
3. Keep at least two off-site backups
4. Update README / architecture diagrams
```

---

## 8. Verification Checklist

### 8.1 Data

```text
papers row count
paragraphs row count
sentences row count
citations row count
claim_cards / evidence
watch_items
users / workspaces
```

### 8.2 Queries

```text
1 exact-title query
1 author query
1 FTS keyword query
1 claim retrieval
1 workspace isolation query
1 watch profile query
```

### 8.3 Concurrency

```text
Follow the Benchmark PostgreSQL Strategy
Run >100-paper/concurrency tests on PostgreSQL only
SQLite allows only small-scale local verification
```

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Migration script accidentally writes to the original database | chmod/read-only the original database; scripts accept only snapshot paths |
| FTS result drift | P3 shadow reads + difference list |
| Dual-write lag | Replay queue + staging soak + health checks |
| Lost writes on rollback | Keep the SQLite dual-write window; dual-write briefly after cutover |
| Long transactions / locks | Connection pool + batch size + timeouts |
| Chinese search degradation | Keep the original text for now; evaluate pg_trgm / external segmentation separately |
| Chroma and PG inconsistency | Stable paper_id; Chroma is not migrated |
| Backups overwritten | Timestamped names + two drives + 30-day retention |

---

## 10. Acceptance Criteria

```text
1. The original research.db was never written by a migration script
2. Before each migration there is an openable backup with integrity_check=ok
3. The SQLite path remains available throughout P1–P3
4. Differences between PG and SQLite for core queries are documented
5. Dual-write staging soak passes (2,422 ops / 0 failed)
6. No P0/P1 incidents for 72h after cutover
7. Rollback drill succeeds
8. 692+ tests pass (no regression during migration)
9. Large-scale/concurrency benchmarks run only on PG
```

---

## 11. Effort Estimates

```text
P0 backup/audit          1 day
P1 schema/adapter        3–5 days
P2 read-only ETL         3–5 days
P3 shadow reads          3–5 days
P4 dual writes           3–5 days
P5 cutover/observation   3–7 days
P6 archival              30-day observation
```

Do not compress P0 or P5.

---

## 12. First Steps

Before writing any migration code, do the following:

```text
1. Generate a snapshot
2. Back up to both drives
3. Run integrity_check
4. Build a row-count inventory
5. Write the inventory to docs/PostgreSQL迁移-基线.md
```

No baseline, no P1.
