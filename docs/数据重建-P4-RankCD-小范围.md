# rank_cd 小范围验证

> Date: 2026-11-01  
> Scope: 5 queries, 8 terms, 100 candidates, `ts_rank_cd`, warm Cross-Encoder.

## Setup

```text
SentenceFTS.search(term_limit=8, top_k=100, ranker="rank_cd")
→ paragraph aggregation
→ bge-reranker-base
→ paper ranking
```

Query set: first 5 cases from `seed_100`.

## Result

| System | Queries | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|
| paragraph_fts | 5 | 1.0000 | 1.0000 | 1.0000 |
| rank_cd 100 + rerank | 5 | 1.0000 | 1.0000 | 1.0000 |

FTS latency:

```text
first run (cold): 1.76s
warm:             0.44s
```

Raw:

```text
eval/results/fts_recall_rerank_cd_100_5q.json
```

## Interpretation

This is a **positive but narrow** result:

```text
- only 5 queries
- all from seed_100
- 100 candidates
- warm FTS below 1 second
```

It does not establish:

```text
- performance on cross_topic / claim_qualifiers / paper_title
- 20-query behavior
- cold-start latency
```

## Decision

```text
Do not switch production yet.
Expand to 5 queries per source, then 20 queries, before any decision.
```

## Next

```text
1. 5 queries per source (20 total)
2. same 8 terms / 100 candidates / rank_cd
3. record cold and warm FTS latency
4. quality gate: Recall@10 must stay >= 0.95
```
