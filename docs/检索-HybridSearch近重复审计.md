# HybridSearch + Near-Duplicate Audit

> Date: 2026-11-01  
> Query set: 20 cases, 5 per source.  
> HybridSearch: no rerank, single-query path.  
> `SCIPAL_NEAR_DUP_THRESHOLD=0.90`.

## Result

| Metric | raw | near-dup 0.90 |
|---|---:|---:|
| paper Recall@10 | 0.9000 | 0.9000 |
| paper MRR | 0.8500 | 0.8500 |
| paper nDCG@10 | 0.8631 | 0.8631 |
| gold paper top10 | 18/20 | 18/20 |
| gold sentence top10 | 6/20 | 6/20 |
| mean unique papers@10 | 4.45 | 4.45 |
| mean max hits/paper | 5.50 | 5.50 |

Raw:

```text
eval/results/hybrid_bias_audit_near_dup.json
```

## Interpretation

Near-duplicate suppression had **no measurable effect** on HybridSearch.

That is not a failure of the dedup utility. It means the redundancy in
HybridSearch is not primarily textual near-duplication:

```text
q001/q015: top10 = 10 paragraphs from one paper
but those paragraphs are lexically distinct
word 3-gram Jaccard < 0.90
```

Paragraph FTS improved `gold sentence 9/20 -> 12/20` because its candidate pool
had more near-identical paragraphs. HybridSearch does not.

## Decision

```text
Keep near-dup opt-in.
Do not claim HybridSearch redundancy is solved.
Text dedup alone is insufficient for document-level clustering.
Next: soft per-document cap / MMR after evidence scoring.
```

## Why This Matters

`unique_papers@10 = 4.45` is unchanged, so HybridSearch still has document-level
concentration. It is topical redundancy, not duplicate text.

The next experiment must operate on **evidence selection**, not just text
similarity.
