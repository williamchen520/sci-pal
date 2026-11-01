# P4 RRF / Multi-Stage Experiment

> Date: 2026-11-01  
> Scope: paper-level fusion of paragraph FTS and sentence FTS → paragraph → cross-encoder.  
> Status: pilot only; no production switch.

---

## 1. Pipeline

```text
paragraph FTS paper ranking
        +
sentence FTS top 5,000
→ best sentence per paragraph
→ top N paragraphs (20 / 50)
→ bge-reranker-base cross-encoder
→ paper ranking
        ↓
paper-level RRF (k=60)
```

Cross-encoder input was capped at 1,500 characters per paragraph.

## 2. Four-query pilot

One query per source (`seed_100`, `cross_topic`, `claim_qualifiers`, `paper_title`):

| System | Queries | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|
| paragraph_fts | 4 | 1.0000 | 0.7500 | 0.8155 |
| multistage_20 | 4 | 1.0000 | 0.7083 | 0.7827 |
| rrf_20 | 4 | 1.0000 | 0.8333 | 0.8750 |
| multistage_50 | 4 | 1.0000 | 0.7083 | 0.7827 |
| rrf_50 | 4 | 1.0000 | 0.8333 | 0.8750 |

Raw report:

```text
eval/results/fts_rrf_pilot.json
```

## 3. Full 20-query multistage

A separate 20-query, 5-paragraph multistage run completed:

| System | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| paragraph_fts | 1.0000 | 0.8806 | 0.9097 |
| sentence_multistage | 0.9000 | 0.8375 | 0.8531 |

The 20-query, 20/50-paragraph RRF run was stopped because the local cross-encoder stalled repeatedly. No result is claimed for that configuration.

## 4. Decision

```text
RRF is promising in the 4-query pilot,
but the evidence is too small and the full run is incomplete.
Do not switch production ranking.
Keep paragraph FTS for paper-level ranking.
```

Next run must use a bounded batch size and a per-query timeout; otherwise cross-encoder latency makes the experiment non-reproducible.
