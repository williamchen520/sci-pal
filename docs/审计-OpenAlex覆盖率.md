# OpenAlex DOI Coverage Audit

> Date: 2026-11-01  
> Data: `data/research.db` (3,310 papers with DOI)  
> Method: OpenAlex `/works?filter=doi:...` in batches of 50  
> Sample: 200 papers, deterministic random seed 42

## 1. Result

```text
papers sampled          200
fetched                 199
missing                   1
coverage_rate         99.5%
errors                    0
```

A deterministic first-200 sample produced the same result:

```text
200 sampled / 199 fetched / 99.5% / 1 missing
```

Raw:

```text
eval/results/openalex_coverage_200_random.json
eval/results/openalex_coverage_200.json
```

## 2. Domain distribution (random 200)

| OpenAlex domain | papers |
|---|---:|
| Health Sciences | 121 |
| Life Sciences | 61 |
| Physical Sciences | 12 |
| Social Sciences | 4 |
| unknown | 1 |

Interpretation:

```text
the corpus is not concentrated in one domain
Health + Life dominate, but Physical/Social are present
this is consistent with a broad 5-domain corpus
```

## 3. Top topics (random 200)

| Topic | papers |
|---|---:|
| Dementia and Cognitive Impairment Research | 20 |
| Gut microbiota and health | 8 |
| Alzheimer's disease research and treatments | 7 |
| Oral microbiology and periodontitis research | 4 |
| Cancer Immunotherapy and Biomarkers | 4 |
| T-cell and B-cell Immunology | 3 |
| Breast Cancer Treatment Studies | 3 |
| Ferroptosis and cancer prognosis | 3 |
| Extracellular vesicles in disease | 3 |
| Chronic Kidney Disease and Diabetes | 3 |

This confirms the long-tail pattern:

```text
top topic  20/199 (~10%)
many topics 2–4 papers
```

## 4. Missing DOI

```text
10.1002/iid3.70560
```

One missing record is not a blocker. It may be:

```text
- not yet indexed
- conference/supplement record
- DOI normalization mismatch
```

## 5. API behavior

Observed:

```text
OpenAlex API reachable
batch of 50 works returned 50 records
no errors in 4 batches
```

OpenAlex returned a free-budget notice:

```text
No API key; shared $0.10/day budget per network
mailto does not raise the limit
```

Recommendation:

```text
set OPENALEX_API_KEY for repeatable production enrichment
set OPENALEX_MAILTO for polite pool
```

Do not commit the key.

## 6. What this proves

```text
OpenAlex can label ~99.5% of sampled papers by DOI
the corpus spans at least 4 OpenAlex domains
the topic distribution is long-tailed
```

## 7. What this does not prove

```text
- primary_topic correctness
- whether topic assignment matches scientific intent
- whether 200-sample coverage extrapolates exactly to 3,310
- whether domain labels will improve retrieval
```

The next check must be label accuracy, not just coverage.

## 8. Recommended next steps

```text
1. Full enrichment: 3,310 papers, batches of 50
2. Store paper_domains (multi-label + primary)
3. Random 100 manual validation
4. Compare OpenAlex with Europe PMC/PubMed MeSH on biomedical subset
5. Re-run domain coverage audit with real labels
6. Only then evaluate domain boost / topic penalty
```

## 9. Data contract

```text
paper_domains
  paper_id
  source              openalex
  openalex_id
  doi
  domain_id / domain_name
  field_id / field_name
  subfield_id / subfield_name
  topic_id / topic_name
  score
  is_primary
  fetched_at
```

## 10. Decision

```text
Coverage is good enough to proceed with OpenAlex enrichment.
Do not treat OpenAlex labels as ground truth yet.
Do not enable domain routing before manual validation.
```

## 11. Script

```bash
python scripts/openalex_coverage.py \
  --limit 200 \
  --sample-seed 42 \
  --out eval/results/openalex_coverage_200_random.json
```

Full run:

```bash
python scripts/openalex_coverage.py \
  --out eval/results/openalex_coverage_summary.json
```

## 12. Full run (2026-11-01)

```text
papers      3,310
fetched     3,290
missing        12
coverage    99.4%
errors          0
```

Domains:

```text
Health Sciences    1,931
Life Sciences      1,156
Physical Sciences    145
Social Sciences       56
unknown                2
```

Stored in `paper_domains_openalex` (3,290 rows) and
`eval/results/openalex_paper_domains.csv`.

Full details: [Full OpenAlex audit](审计-全量OpenAlex与领域标签.md).
