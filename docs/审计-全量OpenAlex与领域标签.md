# Full OpenAlex Enrichment and Domain Audit

> Date: 2026-11-01  
> Data: `data/research.db`  
> Corpus: 3,310 papers, all with DOI  
> Source: OpenAlex `/works?filter=doi:...`

## 1. Full coverage

```text
papers              3,310
fetched             3,290
missing                12
coverage_rate        99.4%
errors                  0
```

Raw:

```text
eval/results/openalex_coverage_summary.json
```

Missing sample:

```text
10.1002/alz70860_102927
10.1192/j.eurpsy.2026.10736
10.1371/journal.pone.0353968
10.4093/dmj.2024.0579.e1
10.21203/rs.3.rs-8921143/v1
...
```

Missing records are mostly preprints, supplements, or not-yet-indexed records.
No enrichment errors occurred.

## 2. OpenAlex domain distribution

| Domain | papers |
|---|---:|
| Health Sciences | 1,931 |
| Life Sciences | 1,156 |
| Physical Sciences | 145 |
| Social Sciences | 56 |
| unknown | 2 |

Interpretation:

```text
Health + Life dominate
Physical/Social exist but are small
the corpus is broader than a single oncology pack
```

## 3. Top topics

| Topic | papers |
|---|---:|
| Dementia and Cognitive Impairment Research | 224 |
| Gut microbiota and health | 194 |
| Cancer Immunotherapy and Biomarkers | 99 |
| Alzheimer's disease research and treatments | 84 |
| Oral microbiology and periodontitis research | 44 |
| Liver Disease Diagnosis and Treatment | 42 |
| Hepatocellular Carcinoma Treatment and Prognosis | 36 |
| CAR-T cell therapy research | 27 |
| Diabetes Treatment and Management | 25 |
| Extracellular vesicles in disease | 25 |

Long tail is strong:

```text
top topic 224/3,290 (~6.8%)
HCC topic 36
many topics 1–3 papers
```

## 4. Persisted labels

CSV:

```text
eval/results/openalex_paper_domains.csv
```

SQLite:

```text
paper_domains_openalex
  rows            3,290
  unique papers   3,290
  source          openalex
```

The existing `paper_domains` table is **not** overwritten. It contains older
`source='auto'` L1 labels.

## 5. Important discovery: auto labels already exist

`paper_domains` already had 3,308 rows with `source='auto'`:

| domain_id | papers |
|---|---:|
| general | 713 |
| microbiology | 684 |
| endocrinology | 641 |
| oncology_other | 623 |
| alzheimers | 517 |
| hcc_io | 130 |

This means the earlier statement “domain labels missing” was incomplete.  
What is missing is **fine-grained subdomain labels**, not all labels.

## 6. Domain audit with auto L1 labels

```text
domain_labels          present (auto, L1 only)
mean_domain_available  228.6
mean_domain_ceiling    1.0
hub_paper_rate         0.237
mean distinct@10       4.45
```

Query-level:

```text
hcc_io queries:        domain_available = 130
oncology_other queries: domain_available = 623
```

At L1, every query has far more than 10 papers in its domain.  
So **coverage ceiling is not visible at L1**; the observed problem is hubness,
not a domain with fewer than 10 papers.

## 7. What is still missing

```text
subfield/topic-level labels for all papers
OpenAlex primary_topic correctness validation
MeSH/Europe PMC cross-check
```

OpenAlex gives topic/subfield, but its assignment is algorithmic.  
We still need a 100-paper manual validation before using it for routing.

## 8. Decision

```text
OpenAlex enrichment: complete (99.4% coverage)
Auto L1 labels: usable for L1 diagnostics
OpenAlex labels: PROVISIONAL, owner waived human review
Fine-grained domain routing: not yet
Production ranking: unchanged
```

## 9. Next

```text
1. Manual 100-paper validation of OpenAlex primary_topic
2. Compare OpenAlex with auto L1 labels
3. Compare OpenAlex with Europe PMC MeSH for biomedical subset
4. Re-run domain coverage audit with topic/subfield labels
5. Only then evaluate domain boost / topic penalty
```

## 10. Files

```text
scripts/openalex_coverage.py
scripts/apply_openalex_domains.py
eval/results/openalex_coverage_summary.json
eval/results/openalex_paper_domains.csv
eval/results/auto_domain_labels.csv
eval/results/domain_coverage_audit_auto.json
```

## 11. ⚠️ Provisional label decision (2026-11-01)

The project owner waived the 100-paper human review for now and accepted
OpenAlex + AI prelabels for **development experiments only**.

```text
human validation: not performed
label status: provisional
production routing: disabled
topic penalty: disabled
```

See [Human validation kit](审计-OpenAlex-100篇人工校验.md) and the prominent
decision block in [Research Logs Index](Research_Logs_Index.md).
