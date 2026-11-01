# OpenAlex 100-Paper Human Validation Kit

> Date: 2026-11-01  
> Status: **⚠️ PROVISIONAL — owner waived human review; AI prelabels accepted for experiments only (0/100 human labels)**  
> Purpose: measure whether OpenAlex `primary_topic` is accurate enough for domain routing.

## 1. Important status

```text
sample rows       100
human labels        0
completed           0/100
```

This document does **not** claim OpenAlex labels are validated.  
The project owner has explicitly waived the 100-paper human review for now and
accepted the AI prelabels for **experimental development only**.

```text
human labels        0/100
owner decision      provisional acceptance
production routing  still disabled
```

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

## 11. AI-assisted prefill (2026-11-01)

Status:

```text
AI prelabels      100/100
human labels        0/100
```

Prelabel distribution:

| topic_match | rows |
|---|---:|
| yes | 72 |
| partial | 16 |
| no | 12 |

Confidence:

| confidence | rows |
|---|---:|
| high | 37 |
| medium | 35 |
| low | 28 |

Europe PMC MeSH hits: 61/100.

Prefilled file:

[eval/validation/openalex_100_prefilled.csv](../eval/validation/openalex_100_prefilled.csv)

Each row carries:

```text
ai_prelabel_domain
ai_prelabel_topic_match
ai_prelabel_confidence
ai_evidence
ai_notes
```

Evidence sources in `ai_evidence`:

```text
OpenAlex work URL
OpenAlex primary_topic / field
DOI
Europe PMC MeSH (when available)
Europe PMC article URL
existing auto_domain_l1
basis for the match decision
```

### Important limitation

This is an **AI-assisted heuristic**, not human validation:

```text
title/abstract token overlap
+ MeSH token overlap
+ auto label corroboration
```

It can be wrong. The `human_*` columns are still blank.

### How to review efficiently

```text
1. Review low-confidence rows first
2. Then all rows with ai_prelabel_topic_match = no
3. Then partial
4. Fill human_domain / human_topic_match / human_notes
5. Run scripts/score_openalex_validation.py
```

## 12. ⚠️ Owner decision: provisional acceptance

On 2026-11-01 the project owner decided:

```text
暂不做 100 篇人工复核，先使用 AI 预标注。
```

Scope:

```text
Allowed: development experiments using OpenAlex / auto L1 / AI prelabel
Not allowed: claiming human validation
Not allowed: production domain routing or topic penalty based on this alone
```

Known risks:

```text
- AI prelabel is heuristic, not ground truth
- 28 low-confidence rows remain unreviewed
- topic errors can propagate into coverage audit
- coverage ceiling / hubness conclusions must stay provisional
```

This decision is also recorded prominently in
[`Research_Logs_Index.md`](Research_Logs_Index.md).
