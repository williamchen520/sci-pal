# SciPal Plugins (M0)

This directory contains plugin manifests, port schemas and adapters.

## Layout

```text
plugins/
├─ manifests/*.yaml   plugin identity, version, entrypoint, license
├─ ports/*.json       core-owned input/output JSON schemas
└─ adapters/*.py      plugin implementations
```

## M0 scope

- trusted in-process execution;
- schema validation before and after `adapter.run(payload)`;
- one JSONL `PluginRun` per call;
- no direct database writes;
- no dynamic install or plugin marketplace.

## Smoke test

```bash
python eval/plugin_bench.py
```

Expected:

```text
plugins: ["echo"]
cases: 2
ok: 2
failed: 0
```

Run log:

```text
logs/plugin_runs.jsonl
```

## Add a plugin

1. Add a port schema under `ports/`.
2. Add an adapter class with `run(payload: dict) -> dict`.
3. Add a manifest under `manifests/`.
4. Run the bench with `--plugins <id>`.

Do not import `services.*` from an adapter unless it is part of the declared
port contract. Research adapters belong to later milestones (A/B/C).
