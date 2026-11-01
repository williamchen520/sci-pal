# End-to-End RRF Loop Profile

> Date: 2026-11-01  
> Scope: 20 queries, 5 per source, warm reranker service.

## Stage timings

| Stage | Mean | Median | Max |
|---|---:|---:|---:|
| Sentence FTS | 9.236s | 9.680s | 15.372s |
| Paragraph aggregate | 0.0009s | 0.0007s | 0.0029s |
| Paragraph text load | 0.2415s | 0.2314s | 0.3461s |
| `/score` 20 | 0.3880s | 0.3749s | 1.0510s |
| `/score` 50 | 0.3636s | 0.3740s | 0.4478s |

Per-query total (including both score counts):

```text
mean 204.6s / 20 queries ≈ 10.2s per query
```

Raw:

```text
eval/results/rrf_loop_profile.json
```

## Finding

The reranker and worker are not the bottleneck:

```text
score20 + score50 ≈ 0.75s per query
text load          ≈ 0.24s per query
```

The bottleneck is sentence FTS:

```text
9.2s average, 15.4s max
```

The earlier single-query profile showed ~1.6s for the first query; the
end-to-end loop is consistently slower because each query builds a 1,000-row
ranked candidate set over 653k sentences.

## Decision

```text
Do not switch production to RRF / sentence ranking.
The next optimization target is sentence FTS query latency, not reranker
startup or inference.
```

## Next hypotheses

1. Reduce `top_k` from 1,000 to 200–300 and check candidate recall.
2. Reduce OR terms to 5–8 and measure latency vs recall.
3. Add a `statement_timeout` and record partial failures.
4. Test `ts_rank_cd` vs `ts_rank` for latency and quality.
5. Pre-filter by `source_type` or paper candidates before ranking.
