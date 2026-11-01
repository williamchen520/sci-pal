# Reranker Single-Query Profile

> Date: 2026-11-01  
> Query: `What is ICI rechallenge in hepatocellular carcinoma?`  
> Candidates: 20 paragraphs; sentence depth 1,000; rerank text capped at 512 characters.  
> Environment: local CPU, isolated `RerankWorker`.

## Result

```text
sentence_search        1.604s
paragraph_aggregate    0.001s
paragraph_text_load    0.391s
worker_start          40.572s
rerank_score           0.667s
total                 43.234s
```

Raw:

```text
eval/results/rerank_profile.json
```

## Interpretation

The reranker inference itself is fast:

```text
20 pairs → 0.667s
```

The dominant cost is **worker startup**:

```text
40.572s = 93.8% of total
```

That explains the earlier full-run behavior:

```text
worker starts slowly
experiment appears idle
startup timeout/restart can repeat
20-query runs never become stable
```

## Next engineering change

Do not create the worker inside the per-run loop. Options:

1. Start one worker, wait for ready, keep it alive for the whole benchmark.
2. Expose a warmup endpoint and record `ready_at`.
3. Use a persistent local reranker service instead of `spawn` per run.
4. Only after warmup, run the 20/50 experiment with per-query timeout and partial reporting.

## Current decision

```text
Production remains on paragraph FTS.
RRF/multistage remains experimental.
No full 20/50 result is claimed.
```
