# Warm Reranker `/score` Latency

> Date: 2026-11-01  
> Service: `scripts/rerank_service.py` on `127.0.0.1:8765`  
> Model: `BAAI/bge-reranker-base`  
> Query: `What is ICI rechallenge in hepatocellular carcinoma?`

## Method

- Build 20 and 50 paragraph candidates from sentence FTS.
- Cap each paragraph text at 512 characters.
- Send each batch to `/score`.
- Use a fresh `RerankClient` per measurement so the client cache does not hide latency.

## Result

| Paragraphs | Run 1 | Run 2 | Mean |
|---:|---:|---:|---:|
| 20 | 0.3831s | 0.1199s | 0.2515s |
| 50 | 0.3049s | 0.3213s | 0.3131s |

Raw:

```text
eval/results/rerank_service_profile.json
```

## Interpretation

```text
A single 20/50-paragraph /score request is fast:
20 → ~0.25s
50 → ~0.31s
```

This confirms:

```text
cold worker startup was the 40s problem
single request inference is not the bottleneck
```

It does **not** explain why the full 20-query loop was still slow. The likely
remaining costs are FTS per query, candidate text loading, and repeated HTTP
round trips; this needs an end-to-end loop profile.

## Decision

```text
Warm service is usable for single-request reranking.
Full 20/50 evaluation is still incomplete.
Production stays on paragraph FTS.
```
