# code-rag module (P1 skeleton)

> Independent `scipal_code` module. No Flask import.

## Current

```text
schema        code_rag v1
service       health
indexing      Python AST + Nextflow block scanner (P2)
search        hybrid code_search (P3)
embeddings    bge-small-zh 512
```

P2 smoke:

```text
scanpy 1.12.5    208 files / 1,819 units / 11,437 edges
nf-core/rnaseq   254 files / 759 units / 143 edges
```

## Schema

```text
code_sources
code_snapshots
code_files
code_units
code_edges
code_embeddings
code_ingest_runs
```

Every row carries `library_id`; code payloads never live in `scipal_core`.

## Migrate

```bash
SCIPAL_CODE_DSN=... python scripts/migrate_code_rag.py
```

## Health

```bash
SCIPAL_CODE_DSN=... python -m code_rag.service health
```

## Embedding

```bash
SCIPAL_CODE_DSN=... python -m code_rag.index --library-id lib_xxx
```

## Resolve calls

```bash
SCIPAL_CODE_DSN=... python -m code_rag.resolve --library-id lib_xxx
```

P2.5 scanpy:

```text
calls 9,127
resolved 1,425 (15.6%)
trace normalize_total -> 4 nodes / 18 edges
```

## HTTP API (UI)

```bash
SCIPAL_CODE_READ_DSN=... python -m code_rag.api --port 5010
```

## Search

```bash
SCIPAL_CODE_READ_DSN=... python -m code_rag.search \
  "normalize total counts" --library-id lib_xxx --top-k 5
```

P3 smoke (10 questions):

```text
Hit@1 0.80
Hit@5 1.00
```

## Ingest

```bash
SCIPAL_CODE_DSN=... python -m code_rag.ingest \
  --repo G:/repos/scanpy-1.12.5 \
  --library-id lib_xxx \
  --repo-url https://github.com/scverse/scanpy \
  --ref 1.12.5 --language python
```

## Manifest

```text
code_rag/manifest.json
```

Capabilities are declared, but only `health` is implemented in P1.
