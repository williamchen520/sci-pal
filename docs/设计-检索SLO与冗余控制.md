# Retrieval SLO and Redundancy Control Design

> **Status**: proposed design, not yet implemented  
> **Date**: 2026-11-01  
> **Scope**: online evidence retrieval for SciPal; paper/paragraph/sentence candidate generation, reranking, evidence packing  
> **Out of scope**: LLM generation latency, offline XML/PDF rebuild, database migration

---

## 1. Context

SciPal currently has two retrieval realities:

```text
Paragraph FTS (SQLite FTS5 BM25)
  paper-level 20-query: 1.0000 / 0.8806 / 0.9097
  but gold sentence top10: 9/20
  and top10 unique papers: 3.85

Sentence FTS on 65万 sentences
  mean 20-query latency: 9.24s
  not viable as an online path

HybridSearch (fixed paper_id)
  paper-level: 0.9000 / 0.8500 / 0.8631
  gold sentence top10: 6/20
  mean unique papers@10: 4.45
```

Two problems must be solved together:

1. A 1-second hard limit for every retrieval path is delaying the project.
2. Relaxing latency will increase candidate volume and worsen document-level redundancy.

The design therefore separates **latency SLO** from **redundancy control**.

---

## 2. Decisions

### D1. Online SLO is 3 seconds p95

```text
Online retrieval + rerank: p95 ≤ 3.0s
Light path (paragraph FTS, no rerank): p95 ≤ 1.0s
Offline indexing / rebuild: no online SLO
```

The 3s SLO applies to:

```text
query preprocessing
candidate retrieval
reranking
deduplication
diversity selection
evidence packing
```

It does **not** include:

```text
LLM answer generation
review writing
PDF/XML parsing
```

### D2. 1 second remains a lightweight-path target

```text
1s is not abandoned.
It is the target for the low-latency path, not for every evidence-heavy path.
```

This keeps the door open for future dedicated low-latency research.

### D3. Do not use hard `max_per_paper=2`

The corrected cap experiment:

```text
unique_papers@10:    3.85 -> 7.50
gold_sentence_top10: 9/20 -> 10/20
```

An earlier audit reported 0/20 because `sentences_fts` rows lacked `para_id`;
that was a measurement bug, now fixed by resolving `sentence_id -> para_id`
through the `sentences` table.

The result is a small positive, not a production mandate: +1 sentence hit, no
HybridSearch or rerank validation. The design still prefers **soft constraints
after evidence scoring**, with cap2 kept as a candidate to test.

### D4. Redundancy is controlled at selection time, not recall time

```text
Recall broad
-> exact dedupe
-> near-duplicate suppression
-> document-aware evidence selection
-> final pack
```

---

## 3. Latency budget

| Stage | Budget | Notes |
|---|---:|---|
| Query normalization | 100 ms | tokenize, normalize, optional keyword extraction |
| Candidate recall | 1,100 ms | FTS and/or vector; target 150–300 candidates |
| Cross-Encoder rerank | 1,400 ms | rerank at most 50 candidates |
| Dedupe + diversity + pack | 400 ms | CPU-only, no model calls |
| **Total p95** | **3,000 ms** | measured from request to evidence response |

Rules:

```text
1. p95, not mean.
2. Cold start is measured separately from warm requests.
3. If the budget is exceeded: drop rerank first, then reduce candidates.
4. If still exceeded: return paragraph FTS results and mark degraded=true.
```

Timeout policy:

```text
SCIPAL_RETRIEVAL_SLO_MS=3000
rerank timeout = min(1400, remaining budget)
hard request timeout = 3500ms
```

---

## 4. Retrieval pipeline

```mermaid
flowchart LR
  Q[Query] --> N[Normalize / keywords]
  N --> R[Broad recall\nFTS + optional vector]
  R --> E[Exact dedupe\nsentence_id / para_id / text]
  E --> ND[Near-duplicate suppression]
  ND --> RR[Cross-Encoder rerank\n≤50 candidates]
  RR --> S[Document-aware selection\nsoft cap + MMR]
  S --> P[Evidence pack]
```

### 4.1 Broad recall

```text
Candidate target: 150–300 sentences or paragraphs
Terms: 8–12
Source filter: only when explicitly requested
```

Do not use unranked `LIMIT 200` as a candidate source. The earlier experiment
showed:

```text
unranked recall: 0.256s
Recall@10:       0.00
```

### 4.2 Exact deduplication

```text
same sentence_id
same para_id
normalized text equality
```

Keep the highest-scoring copy. This is safe and does not remove evidence.

### 4.3 Near-duplicate suppression

```text
scope: within the same paper
similarity: cosine or normalized token Jaccard
threshold: 0.90 (configurable)
keep: highest rerank score
```

Do not suppress across papers unless the text is exactly identical.

### 4.4 Document-aware selection

Use soft constraints, not a hard cap:

```text
min_distinct_papers = 5 (for top10)
max_chunks_per_paper = 3 (final presentation)
guarantee: at least 1 highest-scoring evidence per included paper
```

Selection algorithm:

```text
1. Sort by rerank score.
2. Reserve the best evidence for each high-scoring paper.
3. Apply MMR / xQuAD to fill the remaining slots.
4. Enforce min_distinct_papers before max_chunks_per_paper.
```

MMR starting point:

```text
score = 0.75 * relevance - 0.25 * max_similarity_to_selected
```

The 0.75/0.25 weights are starting values, not constants of nature.

### 4.5 Evidence pack

```text
top 10 evidence items
>= 5 distinct papers when available
<= 3 chunks per paper
each item keeps: paper_id, section_id, para_id, sentence_id, page/bbox or XPath
```

---

## 5. Metrics

### 5.1 Quality

```text
paper_recall@10
paper_mrr
paper_ndcg@10
gold_sentence_recall@10
gold_quote_match
unique_papers@10
max_hits_per_paper@10
near_duplicate_rate
```

### 5.2 Latency

```text
p50 / p95 / p99
per stage
warm and cold separately
degraded_request_rate
rerank_timeout_rate
```

### 5.3 Redundancy

```text
unique_papers@10
max_hits_per_paper@10
near_duplicate_rate
same_paper_share@10
```

A result is not “better” merely because `unique_papers` rises.
It must preserve `gold_sentence_recall`.

---

## 6. Acceptance gates

A retrieval change is eligible for production only if all hold:

```text
p95 end-to-end retrieval ≤ 3.0s
gold_sentence_recall@10 ≥ current paragraph baseline (9/20)
unique_papers@10 ≥ 6
max_hits_per_paper@10 ≤ 3
near_duplicate_rate ≤ 30%
no regression in paper_recall@10
```

Current baseline to beat:

```text
paragraph FTS: paper 1.0000 / 0.8806 / 0.9097
               gold sentence 9/20
               unique papers@10 3.85
```

If a change improves `unique_papers` but reduces `gold_sentence_recall`, it is
rejected. The `max_per_paper=2` experiment is a candidate, not a proven rule.

---

## 7. Rollout plan

```text
Phase 0: offline benchmark on the 20-query set
Phase 1: shadow mode, compare with paragraph FTS
Phase 2: canary 10% traffic
Phase 3: 100%, keep paragraph FTS fallback
```

Rollback:

```text
disable MMR / soft cap
disable rerank
return paragraph FTS
```

No direct production switch from this design.

---

## 8. Configuration plan

Proposed environment variables (not yet wired):

| Variable | Default | Purpose |
|---|---:|---|
| `SCIPAL_RETRIEVAL_SLO_MS` | `3000` | online SLO |
| `SCIPAL_LIGHT_PATH_SLO_MS` | `1000` | no-rerank path |
| `SCIPAL_RETRIEVAL_CANDIDATES` | `200` | broad recall target |
| `SCIPAL_RERANK_CANDIDATES` | `50` | rerank pool |
| `SCIPAL_MAX_CHUNKS_PER_PAPER` | `3` | final evidence pack |
| `SCIPAL_MIN_DISTINCT_PAPERS` | `5` | diversity floor |
| `SCIPAL_NEAR_DUP_THRESHOLD` | `0.90` | near-duplicate suppression |
| `SCIPAL_MMR_LAMBDA` | `0.75` | relevance/diversity tradeoff |

---

## 9. Risks and open questions

```text
1. 3s p95 may still be unattainable on CPU with a large cross-encoder.
2. Near-duplicate threshold needs calibration on scientific text.
3. MMR may reduce evidence completeness for multi-part claims.
4. Gold sentence coverage in the current 20-query set is weak (9/20); a larger
   sentence-level qrels set is required before claiming improvement.
5. The 65万-sentence sentence FTS remains out of the online path.
```

---

## 10. Related documents

- [Document-bias audit](检索-文档级偏置审计.md)
- [HybridSearch bias audit](检索-HybridSearch偏置审计.md)
- [Document-bias solutions](检索-文档级偏置方案调研.md)
- [Two-stage recall](数据重建-P4-两阶段召回.md)
- [Reranker profile](数据重建-P4-Reranker-Profile.md)
- [Research Logs Index](Research_Logs_Index.md)
