# Work Plan: Adaptive Retrieval and Literature Intelligence

> Status: Pending review  
> Scope: Item 1 (user profiles, weekly digests, preventing information cocoons, compute scheduling, legacy data mounts, multi-user permissions)  
> Fit: Research groups first, with support for institute-scale deployments.

## 1. Confirmed Decisions

| Item | Decision |
|---|---|
| User unit | Primarily research groups, compatible with institutes |
| Frequency | Weekly |
| Sources | PubMed / arXiv, among others |
| Ingestion | Articles used in a digest must at minimum have their metadata ingested; PDF/XML is fetched only for OA |
| Non-OA | Metadata only; users can add PDFs manually |
| Profiles | Explicit by default; the user stays in control |
| Click behavior | Used only for deduplication/read status; never auto-edits the profile |
| Presentation | Web first; the first DSH version opens a URL |
| Anti-cocoon | 70/20/10 by default, can be turned off; safety notices retained |
| PPT | Phase 2 |
| Legacy data | Read-only mount plus index; private by default; backup warning required |
| Compute | Local / HPC / cloud by data class |
| PI permissions | Cannot see member profiles or digests; equal-treatment principle |

## 2. Goals

1. Generate one literature digest per week for every user with profiles enabled;
2. 5 in-depth reads + 15 browse items;
3. Driven by explicit profiles that users can edit;
4. 70% core / 20% adjacent / 10% exploratory by default;
5. Digests are private and invisible to PIs;
6. Legacy data can be mounted read-only and indexed;
7. Runs at 1,000 accounts and 100 concurrent requests;
8. Private data never leaves the lab network.

## 3. Non-Goals

- Real-time push;
- Automatically changing user interests;
- PIs monitoring member reading;
- PPT in the first version;
- Cross-lab sharing in the first version;
- Automatic full-text PDF fetching (non-OA) in the first version.

## 4. Overall Flow

```
Weekly schedule
→ load enabled profiles
→ generate search queries
→ pull new items from PubMed / arXiv
→ ingest metadata
→ dedupe / relevance / novelty ranking
→ 70/20/10 quota
→ generate digest
→ display on the web
→ DSH opens the URL
→ user feedback
```

## 5. User Profiles

### 5.1 Fields

```yaml
topics: []            # topic keywords
methods: []           # method keywords
journals: []          # journals to watch
authors: []           # authors to watch
seed_papers: []       # seed papers
exclude_terms: []     # exclusion terms
domain_packs: []      # domain packs
language: zh          # digest language
exploration: 0.1      # exploration ratio
enabled: true
```

### 5.2 Editing

- Edit on the web;
- Extract keywords from seed papers;
- Import BibTeX/DOI;
- Preview the generated query;
- Reset.

### 5.3 No Automatic Profile Changes

Clicks, saves, and ignores:

- Are recorded only as `read/ignored/saved`;
- Are used for deduplication and "don't show what has already been read";
- Are never added to topics automatically;
- Users can manually choose "add to profile".

### 5.4 Project Profiles

- One primary profile per user;
- Additional project profiles are optional;
- The weekly digest uses the primary profile by default;
- Project profiles can be generated separately.

## 6. Sources and Ingestion

### 6.1 Sources

- PubMed E-utilities;
- arXiv API;
- Optionally Europe PMC / bioRxiv / medRxiv;
- Journal RSS can be added later.

### 6.2 Query

The system generates:

```
(topics OR methods OR seed_paper_terms)
AND (date_range = last 7 days)
NOT exclude_terms
```

Users can preview and edit the query before saving it.

### 6.3 Ingestion Policy

Articles accepted into a digest:

- Must have their metadata ingested;
- Published → the global `public` library;
- Preprints/unpublished → per workspace rules, `internal` by default;
- OA → attempt to fetch PDF/XML;
- Non-OA → metadata only;
- Users can add PDFs manually.

### 6.4 Deduplication

Priority order:

1. DOI;
2. PMID;
3. arXiv ID;
4. Title + first author + year;
5. File hash.

## 7. Digest Format

### 7.1 Volume

Default:

```
5 in-depth reads
15 browse items
```

User-adjustable:

```
in-depth reads 3–10
browse items 10–30
```

### 7.2 Fields per Item

```json
{
  "title": "...",
  "journal": "...",
  "date": "2026-10-30",
  "doi": "...",
  "summary": "...",
  "why_relevant": "...",
  "key_finding": "...",
  "evidence": "...",
  "url": "...",
  "category": "core | adjacent | explore",
  "confidence": 0.0
}
```

### 7.3 Grouping

```
This week's must-reads (5)
Worth browsing (15)
Exploratory/contested (within the 10% quota)
Read/ignored
```

### 7.4 Manual Adjustments

- Add to this issue;
- Remove;
- Mark as read;
- Save;
- Add to profile;
- Give "not relevant" feedback.

## 8. Ranking and 70/20/10

### 8.1 Score

```
score = 0.5 * profile_match
      + 0.2 * recency
      + 0.2 * novelty
      + 0.1 * source_quality
```

### 8.2 Classification

| Category | Criteria |
|---|---|
| core | Matches the primary profile's topics/methods |
| adjacent | Same domain pack, different topic |
| explore | Cross-domain-pack / contested / negative results |

### 8.3 Quota

```
70% core
20% adjacent
10% explore
```

Users can:

- Adjust the ratios;
- Turn off explore;
- But safety notices are retained:
  - Retractions;
  - Corrections;
  - Major negative results.

## 9. Preventing Information Cocoons

### 9.1 Mechanisms

- Topic diversity;
- Source diversity;
- Conflicting-viewpoint/conclusion notices;
- Negative results;
- Cross-domain exploration;
- Preprint/peer-review labels.

### 9.2 Metrics

- Topic entropy;
- Source diversity;
- Novelty;
- Cross-domain ratio;
- Save rate;
- Ignore rate;
- Subjective user rating.

### 9.3 Principles

```
Diversity must not come at the cost of relevance
```

Exploratory items are labeled separately and never mixed into "must-reads".

## 10. Compute and Idle-Time Scheduling

### 10.1 Queues

```
interactive > weekly_brief > indexing > backfill
```

### 10.2 Tasks

- Metadata fetching;
- PDF/XML parsing;
- Sentence segmentation;
- Embedding;
- Digest generation;
- Legacy data indexing.

### 10.3 Idle Windows

- Nighttime;
- Idle GPU;
- No interactive requests;
- Manual trigger.

### 10.4 Resources

- Local GPU;
- HPC GPU;
- Cloud for `public` only;
- Per-workspace quota;
- Retries on failure;
- Timeout degradation.

### 10.5 Weekly Digest Generation

- Only for users with `enabled=true` and complete profiles;
- Generated in batches;
- Retries on failure;
- Completed within the generation window.

## 11. Legacy Data Mounts

### 11.1 Method

Read-only mount:

```text
/mounts/legacy/<name>   ro
```

The legacy library is never modified directly.

### 11.2 Process

1. Select the legacy library/directory;
2. Prompt for a backup;
3. Choose `data_class`, private by default;
4. Mount read-only;
5. Build an index;
6. Search, cite, and generate digests from it;
7. Never write back to the legacy library.

### 11.3 Legacy Library Compatibility

- Legacy `research.db`;
- PDF directories;
- BibTeX/RIS;
- Exports from other systems.

### 11.4 Permissions

- Owned by the user who mounted it;
- Private by default;
- Can be explicitly shared to the workspace;
- PIs cannot see private mounts.

## 12. Permissions and Privacy

- Profiles: visible only to the owner;
- Digests: visible only to the owner;
- PIs cannot see member profiles or digests;
- Administrators cannot see content;
- Click behavior is visible only to the user and in aggregate statistics;
- Aggregates never expose individuals.

## 13. Web and DSH

### First Version

```
Web digest page
→ DSH opens the URL
```

### Second Version

```
MCP returns digest items
→ embedded in DSH
```

### Access

- Login;
- Token;
- Workspace permissions;
- No public URLs.

## 14. Data Model

```sql
user_profiles(
  profile_id, user_id, workspace_id,
  name, topics, methods, journals, authors,
  seed_papers, exclude_terms, domain_packs,
  language, exploration, enabled, updated_at
)

profile_projects(profile_id, project_id)

briefs(
  brief_id, profile_id, user_id, workspace_id,
  week_start, status, generated_at
)

brief_items(
  item_id, brief_id, paper_id, category,
  score, rank, why_relevant, status
)

brief_feedback(
  item_id, user_id, action, note, created_at
)

source_queries(
  query_id, profile_id, query_text, source, created_at
)
```

## 15. API

```text
GET  /api/profiles
POST /api/profiles
PUT  /api/profiles/<id>
POST /api/profiles/<id>/preview-query

GET  /api/briefs
GET  /api/briefs/<id>
POST /api/briefs/<id>/generate
POST /api/briefs/items/<id>/feedback

POST /api/mounts
GET  /api/mounts
```

## 16. Evaluation

### Digest Quality

- Human rating of the 5 in-depth reads ≥ 4/5;
- Relevance;
- Novelty;
- Source diversity;
- 70/20/10 compliance;
- Zero privacy leaks.

### System

- Weekly jobs complete within the window;
- 1,000 accounts handled in batches;
- 100 concurrent requests;
- Retries on failure;
- Indexing does not block interactive requests.

## 17. Phases

### P0: Profiles and Digests
- Profile CRUD;
- PubMed/arXiv connectors;
- Metadata ingestion;
- Weekly digest schema;
- Web display.

### P1: Weekly Digest Pipeline
- Scheduled jobs;
- 70/20/10;
- Feedback;
- Deduplication;
- Private permissions.

### P2: Legacy Data Mounts
- Read-only mount;
- Backup warning;
- Index;
- Private by default.

### P3: PPT/Email
- PPT template;
- Email;
- Export.

### P4: DSH Embedding
- MCP digest tools;
- Embedded cards;
- Permission mapping.

## 18. Acceptance Criteria

- Weekly digests are generated on schedule;
- 5+15 items;
- 70/20/10 is configurable;
- Clicks never auto-edit profiles;
- PIs cannot see member profiles or digests;
- Non-OA items carry metadata only;
- Legacy data is mounted read-only;
- Private data never leaves the network;
- 1,000 accounts can run in batches.

## 19. Risks

- PubMed/arXiv rate limits;
- Incomplete metadata;
- Missing full text for non-OA items;
- Quality of exploratory items;
- Weekly job peaks;
- Profile-maintenance fatigue;
- Aggregate statistics leaks;
- LLM cost.

## 20. Open Questions

1. Weekly digest generation day and time zone (proposed: Monday 06:00 Asia/Shanghai).
2. Cap on the number of queries per user per week.
3. Whether users may customize the 5/15 counts.
4. Whether preprints default to `internal` or `public`.
5. Data source for retractions and corrections.
6. Specific templates for the Phase 2 PPT.
7. Whether legacy mounting supports multiple mount points.

## 21. Recommendation

```
Weekly web digest
+ explicit profiles
+ PubMed/arXiv
+ automatic metadata ingestion
+ 70/20/10
+ clicks used only for deduplication
+ private profiles and digests
+ read-only legacy mounts
+ PPT in Phase 2
```
