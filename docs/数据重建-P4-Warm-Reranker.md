# Warm Reranker Service

> Date: 2026-11-01  
> Status: runtime prototype; not used in production.

## 1. Why

Single-query profile showed:

```text
worker_start    40.572s
rerank_score     0.667s
```

The model load, not inference, dominates a cold experiment. The service starts
the model once and reuses it through HTTP.

## 2. Components

```text
scripts/rerank_service.py
services/search/rerank_client.py
```

Endpoints:

```text
GET  /health
POST /score  {"query": "...", "texts": [...], "batch_size": 8}
```

The client has a local score cache and a per-request timeout.

## 3. Validation

Service startup:

```text
READY http://127.0.0.1:8765
GET /health -> 200
```

The service handled multiple `/score` requests, but the full 20/50 experiment
was stopped after 12 score requests because wall-clock throughput was still too
low for a repeatable benchmark on this CPU.

## 4. Decision

```text
The warm service removes per-query worker startup.
It does not remove the CPU cost of real 20/50 paragraph inference.
Production stays on paragraph FTS.
```

## 5. Next

```text
Measure per-request service latency for 20 and 50 real paragraphs.
If latency is acceptable, rerun the full 20-query experiment.
Otherwise use a smaller reranker, ONNX, or GPU.
```
