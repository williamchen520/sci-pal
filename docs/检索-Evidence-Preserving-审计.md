# Evidence-Preserving Selection Audit

> Date: 2026-11-02  
> Query set: 20 cases  
> Candidate depth: 300 paragraphs  
> No production change.

## What Was Built

`services/search/diversity.py`:

```text
select_evidence_preserving(
  reserve_per_paper=1 or 2
  max_per_paper=3
  MMR fill
)
```

Idea:

```text
reserve each paper's best evidence first
then add diversity fill
so a paper cannot be removed before its evidence is considered
```

## Result

| Variant | Recall@10 | MRR | nDCG@10 | gold sentence top10 | unique papers@10 | max hits |
|---|---:|---:|---:|---:|---:|---:|
| raw | 1.0000 | 0.8806 | 0.9097 | 12/20 | 3.85 | 6.80 |
| cap2 | 1.0000 | 0.8806 | 0.9097 | 10/20 | 7.50 | 1.95 |
| cap3 | 1.0000 | 0.8806 | 0.9097 | 10/20 | 6.35 | 2.80 |
| reserve 1 | 1.0000 | 0.8806 | 0.9097 | 5/20 | 10.00 | 1.00 |
| reserve 2 | 0.9500 | 0.8750 | 0.8946 | 10/20 | 5.55 | 2.00 |

Raw:

```text
eval/results/evidence_preserving_audit.json
```

## Interpretation

```text
reserve 1 gives perfect paper diversity
but drops gold sentence to 5/20
reserve 2 recovers gold sentence to 10/20
but loses paper recall and MRR
```

The problem is not that evidence is not reserved. It is that the **gold sentence
is often not the top-ranked paragraph of its paper**, so reserving the paper's
best-scoring paragraph can still miss the answer.

## Decision

```text
Do not adopt evidence-preserving selection.
Do not tune reserve_per_paper on this 20-query set.
Keep paragraph FTS production ranking.
```

## Next

```text
1. build sentence-level evaluation with sentence candidates (not paragraph rollup)
2. test a real reranker over sentence candidates
3. only then revisit diversity
```
