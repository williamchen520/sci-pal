# OpenAlex 100-Paper Human Validation Kit

> Date: 2026-11-01  
> Status: **sample generated; human labels not filled yet (0/100)**  
> Purpose: measure whether OpenAlex `primary_topic` is accurate enough for domain routing.

## 1. Important status

```text
sample rows       100
human labels        0
completed           0/100
```

This document does **not** claim OpenAlex labels are validated.  
The CSV is ready for human review; the conclusions must wait until the
`human_*` columns are filled.

## 2. Sample file

[eval/validation/openalex_100.csv](../eval/validation/openalex_100.csv)

UTF-8 with BOM, Excel-friendly.

Sampling:

```text
seed 42
stratified by OpenAlex domain
Health Sciences      59
Life Sciences        35
Physical Sciences     4
Social Sciences       1
unknown               1
```

## 3. Columns

```text
sample_id
paper_id
doi
title
journal
year
paper_type
openalex_domain
openalex_field
openalex_subfield
openalex_topic
auto_domain_l1
auto_confidence
abstract_snippet
human_domain          <- fill
human_topic_match     <- fill: yes / partial / no
human_notes           <- fill
```

## 4. Review instructions

For each paper, read title + abstract snippet and fill:

### `human_domain`

One of:

```text
Health Sciences
Life Sciences
Physical Sciences
Social Sciences
Other
```

### `human_topic_match`

```text
yes      OpenAlex topic is clearly correct
partial  related but too broad / too narrow
no       wrong topic
```

### `human_notes`

Only when `partial` or `no`; one short sentence.

## 5. Suggested acceptance gates

```text
domain agreement       >= 90%
topic exact/partial    >= 80%
topic exact            >= 60%
```

These are starting gates, not established constants.

## 6. How to compute agreement

After filling:

```bash
python scripts/score_openalex_validation.py \
  --input eval/validation/openalex_100.csv
```

The scorer should report:

```text
domain_agreement
topic_exact_rate
topic_partial_rate
topic_wrong_rate
by_domain_breakdown
```

If the scorer is not implemented yet, use a spreadsheet pivot first.

## 7. What this sample can answer

```text
- whether openalex_domain matches human domain
- whether openalex_topic is too broad/narrow/wrong
- whether mistakes concentrate in a specific domain
```

## 8. What it cannot answer

```text
- retrieval quality
- whether domain routing improves recall
- whether topic penalty helps
```

Those require a separate retrieval experiment.

## 9. Decision

```text
Do not enable domain routing based on this sample alone.
Do not treat auto_domain_l1 as ground truth.
Fill the 100 rows first; then decide.
```

## 10. Related

- [Full OpenAlex audit](审计-全量OpenAlex与领域标签.md)
- [Domain discussion](讨论-领域覆盖与领域感知路由.md)
- [Research Logs Index](Research_Logs_Index.md)
