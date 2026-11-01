# P4 Sentence-Level FTS Evaluation

> Date: 2026-11-01  
> Scope: 20 queries, 5 per source (`seed_100`, `cross_topic`, `claim_qualifiers`, `paper_title`).  
> Metric: retrieve hits, deduplicate to papers in rank order, score Recall@10, MRR, nDCG@10 against `gold_paper_ids`.

---

## 1. Systems

```text
paragraph_fts
  SQLite paragraphs_fts, BM25, OR-of-quoted-terms

sentence_fts
  scipal_v2 sentences.search_vector, ts_rank, OR-of-extracted-terms
  top 5,000 sentence candidates, deduplicated to papers
```

The sentence path is retrieval-only. It does not run refusal or generation.

## 2. Results

| System | Queries | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|
| paragraph_fts | 20 | 1.0000 | 0.8806 | 0.9097 |
| sentence_fts | 20 | 0.9000 | 0.6250 | 0.6943 |

`refusal_accuracy`: not applicable in this retrieval-only run.

Raw report:

```text
eval/results/fts_sentence_compare.json
```

## 3. Interpretation

```text
sentence FTS improves exposure of individual sentences but ranks papers worse.
Short sentences and repeated matches create a flatter, noisier paper ranking.
```

Observed:

```text
- Recall@10 drops from 1.00 to 0.90
- MRR drops from 0.8806 to 0.6250
- nDCG@10 drops from 0.9097 to 0.6943
```

## 4. Decision

```text
Do not switch the production paper ranker to sentence FTS yet.
Keep paragraph FTS for paper-level ranking.
Keep sentence FTS for traceability and sentence-level evidence.
```

This follows the project stop rule: do not tune further after a negative result without a new hypothesis.

## 5. Next hypothesis

Possible next experiment, only if needed:

```text
sentence FTS for candidate recall
→ aggregate to paragraph with max sentence rank
→ rerank paragraphs with the existing cross-encoder
→ aggregate to papers
```

That is a multi-stage retrieval change, not a tokenizer change, and needs its own evaluation.

## 6. Multi-stage experiment

Pipeline:

```text
sentence FTS (top 5,000)
→ best sentence per paragraph
→ top 5 paragraphs
→ bge-reranker-base cross-encoder
→ deduplicate to papers in rerank order
```

Cross-encoder input text was capped at 1,500 characters for bounded, reproducible latency.

| System | Queries | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|
| paragraph_fts | 20 | 1.0000 | 0.8806 | 0.9097 |
| sentence_multistage | 20 | 0.9000 | 0.8375 | 0.8531 |

Raw report: `eval/results/fts_multistage_compare.json`.

The multi-stage path recovers most of the ranking quality lost by direct sentence ranking, but it still does not beat paragraph FTS. It remains an experimental path.
