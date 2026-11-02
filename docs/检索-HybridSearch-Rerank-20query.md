# HybridSearch + Rerank: 20-Query Evaluation

> Date: 2026-11-02  
> Query set: 20 cases, 5 per source  
> Retrieval: HybridSearch (FTS + vector + RRF)  
> Reranker: warm bge-reranker-base over HTTP

## 1. Setup

```text
HybridSearch candidate path: vector + FTS5 + RRF
reranker: scripts/rerank_service.py
model: BAAI/bge-reranker-base
candidate pool: max(top_k * 4, 20)
```

The reranker was started once and kept warm; the 20 queries reused it.

## 2. Results

| System | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| paragraph FTS | 1.0000 | 0.8806 | 0.9097 |
| HybridSearch no-rerank | 0.9000 | 0.8500 | 0.8631 |
| **HybridSearch + rerank** | **1.0000** | **0.8583** | **0.8946** |

Raw:

```text
eval/results/hybrid_20_query_rerank.json
```

## 3. What Improved

```text
Recall@10   0.9000 -> 1.0000
MRR         0.8500 -> 0.8583
nDCG@10     0.8631 -> 0.8946
```

The reranker recovered the paper that no-rerank missed (q010 / claim q1)
and improved ranking on several queries.

## 4. Remaining Gap vs Paragraph FTS

```text
MRR      0.8583 vs 0.8806  (-0.0223)
nDCG@10  0.8946 vs 0.9097  (-0.0151)
```

Per-case weak spots:

```text
q009     MRR 0.500
q014     MRR 0.333
q015     MRR 0.500
claim_hcc_triple_os__q1       MRR 0.500
claim_hcc_triple_os__q2       MRR 0.333
```

The reranker does not fix these; they are candidate/ordering issues.

## 5. Caveats

```text
paper-level metrics only
gold sentence not measured here
only 20 queries
one run
latency not recorded in this run
```

Do not claim the hybrid path is production-ready from this table alone.

## 6. Decision

```text
Paragraph FTS remains production ranking.
HybridSearch + rerank is now a credible candidate.
Next gate: gold_sentence_recall + p95 latency on the same 20 queries.
```

## 7. Next

```text
1. add gold sentence rank to hybrid rerank evaluation
2. record per-query latency and p95
3. compare with 3s SLO
4. only then consider canary
```

## 8. Gold sentence + latency (2026-11-02)

Same 20 queries, warm reranker service:

| Metric | Hybrid + rerank |
|---|---:|
| Recall@10 | 1.0000 |
| MRR | 0.8583 |
| nDCG@10 | 0.8946 |
| gold sentence top10 | **7/20** |
| latency mean | **3.0511s** |
| latency p50 | **1.9539s** |
| latency p95 | **3.2612s** |

Raw:

```text
eval/results/hybrid_20_query_rerank_sentence.json
```

### What this means

```text
paper-level recall is 1.0
gold sentence is only 7/20
p95 is 3.26s, above the 3s SLO
```

So the hybrid rerank path is **not** production-ready:

```text
it finds the paper more reliably than no-rerank
but it does not find the answering sentence
and it misses the p95 latency budget
```

### Decision

```text
Keep paragraph FTS production.
Do not canary HybridSearch + rerank yet.
Next: evidence-preserving candidate selection + latency reduction.
```
