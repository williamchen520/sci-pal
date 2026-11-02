# Sentence-Level Retrieval Evaluation

> Date: 2026-11-02  
> 20 queries, 5 per source  
> Read-only; no production switch.

## Setup

```text
paragraph baseline : SQLite paragraphs_fts, top 300 paragraphs
sentence candidate : PostgreSQL scipal_v2 sentences.search_vector, top 100
gold sentence       : exact sentence_id match
```

Script:

```text
scripts/sentence_20_query.py
```

Raw (corrected):

```text
eval/results/sentence_20_query_mapped.json
```

## Results

| System | Recall@10 | MRR | nDCG@10 | gold sentence top10 | gold para top10 | mean latency | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| paragraph FTS | 1.0000 | 0.8806 | 0.9097 | — | 12/20 | 0.3138s | 0.6222s |
| sentence FTS (top 100) | 0.9000 | 0.6250 | 0.6943 | **9/20** | 0/20 | **16.84s** | **24.92s** |

## Interpretation

```text
sentence FTS is worse on every ranking metric
it did not put any exact gold sentence in the top 10
it is ~55x slower at the mean and ~55x slower at p95
```

The first run reported `0/20` gold sentence. That number was wrong: the gold
sentence IDs came from SQLite while the sentence index lives in PostgreSQL
`scipal_v2`, and the two stores use different sentence_id formats. All 17 gold
sentences were found in PG by exact text, with **0/17 matching IDs**.

After mapping gold sentence text to PG IDs, the corrected sentence-level result
is **9/20**. That is still below paragraph FTS (12/20 paragraphs), but it is not
zero.

## Root Cause of the 0/20 Artifact

```text
SQLite:
  XML  ..._00015_sent_001
  PDF  ..._para_..._sent_005

PostgreSQL scipal_v2:
  XML  ..._00016_sent_001
  PDF  sent_..._001104
```

All 17 gold sentences:

```text
same sentence_id : 0
exact text match : 17/17
```

So the original zero measured **ID mismatch**, not retrieval quality. The
evaluation must map by `(paper_id, text)` or the pipeline must make sentence IDs
stable across stores.

## Decision

```text
Do not use sentence FTS for production ranking.
Do not build a UI path on the 650k-sentence index.
Keep paragraph FTS production.
```

Reasons that survive the correction:

```text
paper-level Recall/MRR/nDCG are still worse
gold sentence 9/20 vs 12/20 paragraph-gold
p95 24.9s vs 0.47s paragraph FTS
```

## Next

```text
1. inspect why sentence query terms are too broad (term extraction / tsquery)
2. test sentence FTS only as a candidate source with a much smaller query
3. if it still loses, stop this line
```
