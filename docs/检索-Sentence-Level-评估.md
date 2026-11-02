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

Raw:

```text
eval/results/sentence_20_query.json
```

## Results

| System | Recall@10 | MRR | nDCG@10 | gold sentence top10 | gold para top10 | mean latency | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| paragraph FTS | 1.0000 | 0.8806 | 0.9097 | — | 12/20 | 0.3138s | 0.6222s |
| sentence FTS (top 100) | 0.9000 | 0.6250 | 0.6943 | **0/20** | 0/20 | **17.17s** | **34.41s** |

## Interpretation

```text
sentence FTS is worse on every ranking metric
it did not put any exact gold sentence in the top 10
it is ~55x slower at the mean and ~55x slower at p95
```

The zero gold-sentence count is not a ranking tie: the exact gold sentence does
not appear in the top 100 at all for these queries.

## Decision

```text
Do not use sentence FTS for production ranking.
Do not build a UI path on the 650k-sentence index.
Keep paragraph FTS production.
```

## Next

```text
1. inspect why sentence query terms are too broad (term extraction / tsquery)
2. test sentence FTS only as a candidate source with a much smaller query
3. if it still loses, stop this line
```
