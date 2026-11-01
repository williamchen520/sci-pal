# Sentence FTS Latency Experiment

> Date: 2026-11-01  
> Scope: reduce the 9.2s sentence-FTS stage found in the RRF loop profile.

## 1. Query variants

Direct SQL variants on the representative query:

| Terms | Top-K | Ranker | Latency |
|---:|---:|---|---:|
| 5 | 200 | ts_rank | 0.837s |
| 5 | 200 | ts_rank_cd | 0.181s |
| 5 | 500 | ts_rank | 0.264s |
| 8 | 500 | ts_rank | ~0.2s |
| 12 | 1,000 | ts_rank | 0.186s |

All warmed variants were below 0.3s.

## 2. Source filter fix

The original query used:

```sql
AND (%s::text IS NULL OR s.source_type = %s)
```

Even with `None`, this can produce a poor plan. Replaced with a dynamically
built predicate that omits the source filter when it is not needed.

Single-query `SentenceFTS` latency:

```text
before: 1.11s / 9s observed in the loop
after:  0.49s
```

## 3. What remains

The end-to-end 20-query loop still reported:

```text
sentence_search mean 9.24s
total_mean         204.3s
```

The reason it still shows the old number needs a separate audit:

```text
- per-query connection setup
- stale process/cached module
- concurrent database activity
- query-specific term cardinality
```

No production switch is justified yet.

## 4. Decision

```text
Keep paragraph FTS for production paper ranking.
Keep sentence FTS experimental.
Next: reproduce the loop in one process with per-query stage logs and verify the
source-filter fix is actually loaded.
```
