# code-rag module (P1 skeleton)

> Independent `scipal_code` module. No Flask import.

## Current

```text
schema        code_rag v1
service       health
indexing      Python AST + Nextflow block scanner (P2)
search        not implemented
embeddings    not implemented
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
