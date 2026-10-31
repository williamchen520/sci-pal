# SciPal Plugins (M0/M1)

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

## M1: ClaimVerifierPort

Adapters:

```text
claim-verifier-nli             existing LLM NLI (network optional)
claim-verifier-rule            deterministic cue baseline
claim-verifier-underdetermines smoke baseline
```

Benchmark:

```bash
python eval/claim_verifier_bench.py
```

Initial result on 10 claims / 11 evidence:

```text
rule accuracy          0.3636
underdetermines        0.0000
majority baseline      0.9091
```

The dataset is imbalanced; this run validates the contract, not algorithm quality.

## M2: RetrieverPort

Adapters:

```text
retriever-bm25              FTS5/BM25
retriever-dense             Chroma dense
retriever-hybrid            BM25 + dense + RRF
retriever-hybrid-rerank     hybrid + cross-encoder
```

Benchmark:

```bash
python eval/retriever_bench.py
```

Mixed result on 74 queries / 100 papers:

```text
bm25        Recall@10 0.9459  MRR 0.8149
dense       Recall@10 0.9324  MRR 0.8829
hybrid      Recall@10 0.9459  MRR 0.9036
hybrid+rr   Recall@10 0.9865  MRR 0.9081
```

The query set now includes 20 cross-topic queries and 48 distractor papers, but
is still not a publication-grade benchmark.

## Add a plugin

1. Add a port schema under `ports/`.
2. Add an adapter class with `run(payload: dict) -> dict`.
3. Add a manifest under `manifests/`.
4. Run the bench with `--plugins <id>`.

Do not import `services.*` from an adapter unless it is part of the declared
port contract. Research adapters belong to later milestones (A/B/C).
