# code-rag module (P1 skeleton)

> Independent `scipal_code` module. No Flask import.

## Current

```text
schema        code_rag v1
service       health only
indexing      not implemented
search        not implemented
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

## Manifest

```text
code_rag/manifest.json
```

Capabilities are declared, but only `health` is implemented in P1.
