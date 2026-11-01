# HybridSearch 20-query Baseline

> Date: 2026-11-01  
> System: existing `HybridSearch` (FTS5 + Chroma + RRF + Cross-Encoder)  
> Data: `data/research.db`  
> Query set: 20 cases, 5 per source.

## Result

| System | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| paragraph_fts | 1.0000 | 0.8806 | 0.9097 |
| HybridSearch + rerank | 0.7000 | 0.6417 | 0.6565 |

Raw:

```text
eval/results/hybrid_20_query.json
```

Command:

```powershell
venv_sciPal_py312\Scripts\python.exe scripts\hybrid_20_query.py `
  --out eval\results\hybrid_20_query.json
```

## Per-source failures

Failures were concentrated in:

```text
cross_topic
claim_qualifiers
paper_title
```

Several queries returned no gold paper at all. This is not a latency tradeoff;
it is a retrieval-quality problem in the current hybrid path.

## Interpretation

The existing hybrid search is **not** a drop-in improvement over paragraph FTS
on this 20-query set. The vector/FTS/RRF fusion and reranker are losing papers
that paragraph FTS retrieves.

Possible causes:

```text
- paragraph FTS covers all legacy sections; Chroma index may lag data
- RRF weights favor vector results
- cross-encoder candidate pool too small
- v2 XML/PDF rebuild is not yet the source for HybridSearch
```

## Decision

```text
Do not switch production ranking to HybridSearch based on this run.
Keep paragraph FTS as the current production baseline.
Next: compare per-query missing papers and check Chroma freshness.
```
