# Soft Cap and MMR Audit

> Date: 2026-11-02  
> Query set: 20 cases, 5 per source  
> Candidate depth: 300 paragraphs  
> No production change.

## Result

| Variant | Recall@10 | MRR | nDCG@10 | gold sentence top10 | unique papers@10 | max hits/paper |
|---|---:|---:|---:|---:|---:|---:|
| raw top10 | 1.0000 | 0.8806 | 0.9097 | 12/20 | 3.85 | 6.80 |
| soft cap 2 | 1.0000 | 0.8806 | 0.9097 | 10/20 | 7.50 | 1.95 |
| soft cap 3 | 1.0000 | 0.8806 | 0.9097 | 10/20 | 6.35 | 2.80 |
| MMR cap3 (λ=.75) | 0.8500 | 0.8250 | 0.8315 | 5/20 | 7.25 | 2.45 |

Raw:

```text
eval/results/soft_cap_mmr_audit.json
```

## Interpretation

### Soft cap 2 / 3

```text
paper recall unchanged
unique papers improves strongly
gold sentence drops 12 -> 10
```

So the cap is a **tradeoff**, not a free win.

### MMR λ=.75

```text
paper recall 1.0 -> 0.85
gold sentence 12 -> 5
unique papers 7.25
```

MMR with this weight is **rejected**:

```text
it maximizes diversity at the expense of the answering evidence
```

### Document-level bias remains real

```text
raw max hits/paper = 6.8
```

A small number of papers dominate the raw top10.

## Decision

```text
Do not enable soft cap or MMR in production.
Do not tune MMR lambda on this 20-query set.
Keep paragraph FTS as production baseline.
```

## Next

```text
1. Try evidence-preserving selection: reserve gold-relevant candidate before diversity
2. Evaluate on a larger, domain-stratified query set
3. Only then consider a canary
```
