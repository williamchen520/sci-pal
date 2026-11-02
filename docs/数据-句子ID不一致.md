# Data Issue: Sentence IDs Differ Between SQLite and PostgreSQL

> Date: 2026-11-02  
> Status: confirmed; not fixed.

## Evidence

All 17 gold sentences from the 20-query set:

```text
same sentence_id : 0/17
exact text match : 17/17
```

Examples:

```text
SQLite  para_paper_PMC13616637_ab84d6de_xml_00015_sent_001
PG v2   para_paper_PMC13616637_ab84d6de_xml_00016_sent_001

SQLite  para_paper_PMC13612676_5962339f_0003_sent_005
PG v2   sent_paper_PMC13612676_5962339f_001104
```

## Why It Matters

```text
1. sentence-level evals cannot join gold IDs by sentence_id
2. evidence pages cannot round-trip a SQLite sentence to a PG sentence
3. any cross-store claim/evidence link must use (paper_id, text) or a stable ID
```

## Immediate Impact

The first sentence-FTS evaluation reported `gold_sentence 0/20`; this was an ID
mismatch artifact. After mapping by `(paper_id, text)`, the corrected result is
`9/20`.

## Remediation Options

```text
A. make the parser emit stable sentence IDs in both stores
B. store a content hash / stable sentence key in both schemas
C. add a mapping table keyed by (paper_id, text_hash)
```

Do not build joins on the current sentence_id across stores.

## Next

```text
1. trace where the XML paragraph index shifts (+1)
2. trace where PDF sentence IDs switch from para_*_sent_* to sent_*
3. choose A/B/C and backfill
```
