# HybridSearch Bias Audit

> Date: 2026-11-01  
> Data: `data/research.db`  
> Query set: 20 cases, 5 per source.  
> HybridSearch: no rerank, single-query path.

## Result

```text
cases                              20
gold papers per query               1
queries with multiple gold papers   0

paper Recall@10                    0.9000
paper MRR                          0.8500
paper nDCG@10                      0.8631

gold paper in top10                18 / 20
gold sentence in top10              6 / 20

mean unique papers@10               4.45
mean max hits per paper             5.50
```

Raw:

```text
eval/results/hybrid_bias_audit.json
```

## Per-query examples

```text
q001  top10 papers = 1   max hits/paper = 10  gold sentence = None
q004  top10 papers = 2   max hits/paper = 9   gold sentence = rank 2
q015  top10 papers = 1   max hits/paper = 10  gold sentence = None
claim_hcc_dtace_haic__q1  top10 papers = 1  max hits/paper = 10  gold sentence = rank 7
```

## Interpretation

### 1. Paper-level score is misleading

```text
paper Recall@10 = 0.9000
gold sentence top10 = 0.3000 (6/20)
```

The paper can be present while the answering sentence is missing.

### 2. Top10 is document-skewed

Mean unique papers in top10 is only:

```text
4.45 / 10
```

Some queries return 10 paragraphs from **one paper**:

```text
q001, q015, claim_hcc_dtace_haic__q1, claim_hcc_dtace_haic__q2, title_946
```

That is true document-level redundancy, not just a theoretical risk.

### 3. Paragraph FTS comparison

For the same 20-query set, paragraph FTS had:

```text
paper Recall@10        1.0000
unique_papers@10      10.00
gold_sentence_top10    9 / 20
max hits/paper       118.4 (candidate pool)
```

HybridSearch is less document-skewed at top10 than the raw paragraph
candidate pool, but it loses more gold papers and sentences.

## Decision

```text
Do not evaluate or tune HybridSearch on paper Recall alone.
Report unique_papers@10, max hits/paper, and gold sentence rank.
Production remains on paragraph FTS.
```

## Next

```text
1. Add max_per_paper = 1 or 2 before paper-level scoring.
2. Compare raw ranking vs capped ranking.
3. Make sentence-level gold the primary gate.
```
