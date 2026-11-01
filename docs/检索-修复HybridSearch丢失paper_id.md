# HybridSearch Recall Loss: Missing `paper_id`

> Date: 2026-11-01  
> Symptom: HybridSearch 20-query baseline scored .7000/.6417/.6565 while paragraph FTS scored 1.0000/.8806/.9097.

## Root cause

`HybridSearch.vector_search()` returned:

```json
{
  "para_id": "...",
  "text": "...",
  "metadata": {"paper_id": "..."},
  "score": 0.78
}
```

But it did **not** put `paper_id` at the top level.

`rrf_fuse()` groups by top-level `paper_id`, so every vector hit was grouped under
`None`. The fused list was dominated by a single `None` bucket, and paper-level
evaluation could not see the gold paper even when the vector hit existed.

This is a code bug, not an index freshness problem.

## Fix

`vector_search()` now copies provenance into the hit:

```python
"paper_id": meta.get("paper_id"),
"section_l1": meta.get("section_l1"),
"section_l2": meta.get("section_l2"),
```

## Validation

Query:

```text
What are the main global challenges in colorectal cancer burden despite screening?
```

Before:

```text
vector: paper_id = None for every hit
hybrid: paper_id = None
```

After:

```text
vector:
  paper_PMC13630772_2fd56d48_xml
  paper_PMC13631563_4e18eb11_xml  ← gold, rank 2
  ...

hybrid:
  same valid paper IDs; gold is present
```

The full 20-query baseline was not rerun because the local Chroma + embedding
model run exceeded the practical timeout. The regression is proven at the
query level; the 20-query number must be regenerated before any production
decision.

## Decision

```text
Keep production on paragraph FTS until the fixed HybridSearch baseline is rerun.
Do not claim the hybrid path is fixed end-to-end yet.
```

## Next

```text
1. Run scripts/hybrid_20_query.py --no-rerank on the fixed code.
2. Then run with --rerank.
3. Compare per-case gold ranks; verify the None bucket is gone.
```

## 7. Fixed HybridSearch rerun (no rerank)

```text
paragraph_fts       1.0000 / 0.8806 / 0.9097
hybrid (fixed)      1.0000 / 0.9250 / 0.9446
```

Raw:

```text
eval/results/hybrid_20_query_fixed_norerank.json
```

The `None` bucket is gone. Gold paper is now present for all 20 queries.
The hybrid path beats paragraph FTS on MRR and nDCG at the same Recall@10.

The cross-encoder pass is still slow on the local CPU and has not been rerun.
Do not switch until that pass completes.
