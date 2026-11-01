# Work Plan: Plugin Ports and Comparative Benchmarking

> Date: 2026-10-31  
> Status: Plan, no implementation  
> Goal: Let external algorithms and tools plug into the SciPal platform, run comparative tests under one shared protocol, and turn that into publishable engineering-application research.

---

## 1. Background and Assessment

### 1.1 The Problem

External teams keep releasing new:

- retrieval/reranking algorithms;
- claim verification / NLI / CoE methods;
- paper generation / writing tools;
- evaluation protocols.

If every integration means editing `routes/`, `services/`, the database, and the UI, three problems follow:

1. Not comparable: each integration has its own inputs, outputs, and budget;
2. Not reproducible: there is no record of plugin version, configuration, or data snapshot;
3. Not publishable: we can only write "we integrated X", never "under a unified protocol, X outperforms Y".

### 1.2 Assessment

> This is not "adding an API" but establishing four things:  
> **contract + registry + isolation + evaluation.**

The platform defines the ports; a plugin may only implement the contract and must not modify the platform.

---

## 2. Goals and Non-Goals

### 2.1 Goals

```text
1. Define stable plugin port contracts
2. Build manifest / registry / loader
3. Build a unified comparative benchmarking harness
4. Record full provenance for every plugin run
5. Land the three ports in the order A → B → C
6. Produce material for an engineering-application paper
```

### 2.2 Non-Goals

```text
No plugin marketplace
No dynamic pip install
No execution of untrusted arbitrary code
No one-click paper
No plugin side effects on claim status
No direct plugin reads or writes of SQLite
```

---

## 3. Overall Architecture

```text
SciPal platform
  ├─ Port contracts (owned by core)
  ├─ Plugin Registry (manifest loading)
  ├─ Plugin Runner (isolation/timeout/logging)
  └─ Evaluation Harness (unified comparison)

plugins/
  ├─ manifests/
  │   ├─ claim-verifier-base.yaml
  │   ├─ retriever-bm25.yaml
  │   └─ paper-generator-base.yaml
  └─ adapters/
      ├─ claim_verifier_base.py
      ├─ retriever_bm25.py
      └─ paper_generator_base.py
```

### 3.1 The Four Core Objects

```text
PortContract   interface and schema
PluginManifest identity, version, capabilities, resources, license
PluginRun      input/output/latency/cost of one invocation
BenchmarkSpec  dataset, metrics, budget, seed
```

### 3.2 Run Records

Every plugin invocation writes JSONL:

```json
{
  "run_id": "run_...",
  "plugin_id": "claim-verifier-base",
  "plugin_version": "0.1.0",
  "port": "claim_verifier",
  "dataset_hash": "sha256:...",
  "config": {},
  "seed": 42,
  "latency_ms": 1200,
  "cost_usd": 0.003,
  "output": {},
  "error": null
}
```

This is **artifact-level provenance**, and also the basis for the later CoE chain audit.

---

## 4. Stage A: ClaimVerifierPort

### 4.1 Goal

Compare different claim verification methods on the same batch of claims + evidence:

- the existing LLM NLI;
- a rule/keyword baseline;
- external NLI / CoE tools.

### 4.2 Contract

```python
class ClaimVerifierPort(Protocol):
    name: str
    version: str

    def verify(
        self,
        claim: ClaimInput,
        evidence: list[EvidenceInput],
        *,
        options: dict,
    ) -> ClaimVerification:
        ...
```

Input:

```json
{
  "claim_id": "claim_hcc_triple_os",
  "claim_text": "...",
  "qualifiers": {},
  "evidence": [
    {
      "evidence_id": "paper_..._sent_001",
      "quote": "...",
      "paper_id": "paper_...",
      "study_type": null,
      "endpoint": null
    }
  ]
}
```

Output:

```json
{
  "relation": "refutes",
  "confidence": 0.82,
  "rationale": "...",
  "evidence_ids": ["paper_..._sent_001"],
  "limitations": ["OS immature"],
  "plugin": {"id": "...", "version": "..."},
  "latency_ms": 1200
}
```

### 4.3 Adapters

| Adapter | Description |
|---|---|
| `claim-verifier-base` | Wraps the existing `services/claims/nli.py` |
| `claim-verifier-rule` | Rule/directional-word baseline |
| `claim-verifier-underdet` | Pipeline-validation stub that always returns `underdetermines` |

### 4.4 Dataset

```text
10 claims
32-paper corpus
5 existing underdetermines + 1 refutes
human-reviewed relations as gold
```

### 4.5 Metrics

```text
relation accuracy
macro-F1 (supports/refutes/underdetermines)
refutes precision / recall
underdetermines recall
latency
cost
human rating of rationale, 1-5
```

### 4.6 Acceptance

```text
1. All three adapters go through the same contract
2. The same claim/evidence batch can be rerun
3. Every run writes JSONL
4. No writes to claim status, no writes to the evidence table
5. A comparison table is produced
6. Tests for the new port and adapters
7. The 677 existing tests plus the new tests pass
```

### 4.7 Risks

- 10 claims is too few; statistical power is insufficient;
- LLM output is unstable and needs a fixed seed/temperature;
- There is only one `refutes` gold item, so recall is unreliable.

Mitigation:

```text
Validate the pipeline first; do not rush to a "who is better" conclusion;
expand the claim set at the paper stage.
```

---

## 5. Stage B: RetrieverPort

### 5.1 Goal

Compare under a shared corpus / query / top_k:

- BM25;
- dense;
- hybrid RRF;
- hybrid + rerank;
- external retrieval algorithms.

### 5.2 Contract

```python
class RetrieverPort(Protocol):
    name: str
    version: str

    def retrieve(
        self,
        query: str,
        *,
        corpus: list[str],
        top_k: int,
        options: dict,
    ) -> list[Candidate]:
        ...
```

Output:

```json
{
  "candidates": [
    {
      "paper_id": "...",
      "node_id": "...",
      "text": "...",
      "score": 0.82,
      "rank": 1
    }
  ]
}
```

### 5.3 Adapters

| Adapter | Description |
|---|---|
| `retriever-bm25` | FTS5/BM25 only |
| `retriever-dense` | Chroma only |
| `retriever-hybrid` | RRF |
| `retriever-hybrid-rerank` | Platform default |
| `retriever-external` | External retriever |

### 5.4 Dataset

```text
eval/gold/seed_100.jsonl
+ claim-derived queries
+ fixed snapshot of the 32-paper corpus
```

### 5.5 Metrics

```text
Recall@10
MRR
nDCG@10
evidence coverage
latency
```

### 5.6 Acceptance

```text
1. Same query set, same corpus hash
2. All five adapters emit the same schema
3. Comparison table + failure case analysis
4. Existing `/api/retrieve` behavior is unchanged
5. Tests pass
```

### 5.7 Risks

- Candidate granularity differs across retrievers (paragraph vs. sentence);
- Everything must be normalized to `node_id`;
- Dense retrieval depends on the Chroma index, so the snapshot must be fixed.

---

## 6. Stage C: PaperGeneratorPort

### 6.1 Goal

Compare different writing methods under claim + evidence + writing brief constraints:

- a template/deterministic baseline;
- the platform LLM + writing brief;
- external paper generation tools.

### 6.2 Contract

```python
class PaperGeneratorPort(Protocol):
    name: str
    version: str

    def generate(
        self,
        *,
        section_plan: dict,
        claims: list[ClaimInput],
        evidence: list[EvidenceInput],
        writing_brief: dict,
        options: dict,
    ) -> Draft:
        ...
```

Output:

```json
{
  "sentences": [
    {
      "text": "...",
      "claim_ids": ["..."],
      "evidence_ids": ["..."],
      "rhetorical_role": "assertion"
    }
  ]
}
```

Hard constraints:

```text
Every assertion sentence must have evidence_ids
must_not_write must not appear
Contested claims must state their qualifiers
```

### 6.3 Adapters

| Adapter | Description |
|---|---|
| `paper-generator-template` | Deterministic baseline that does not call an LLM |
| `paper-generator-base` | Platform LLM + writing brief |
| `paper-generator-external` | External paper generation tool |

### 6.4 Dataset

```text
3 section plans
10 claims
32-paper corpus
human rubric
```

### 6.5 Metrics

```text
sentence evidence coverage
unsupported claim rate
citation precision
forbidden phrase rate
human rating (argument quality / readability)
latency / cost
```

### 6.6 Acceptance

```text
1. Assertion sentences without an evidence_id are blocked
2. must_not_write is blocked
3. All three adapters share the same schema
4. Blind human evaluation by at least two raters
5. No automatic claim status writes
6. Tests pass
```

### 6.7 Risks

- Generation quality is subjective to evaluate;
- External tools may not be reproducible;
- It is easy to slide toward "one-click paper".

Mitigation:

```text
Section-level only, never whole papers;
build the writing gate first, then run the generation comparison.
```

---

## 7. Unified Evaluation Harness

### 7.1 Command

```bash
python eval/plugin_bench.py \
  --port claim_verifier \
  --plugins claim-verifier-base,claim-verifier-rule \
  --dataset eval/claims/pilot_10.json \
  --out eval/results/plugin_claim_verifier.jsonl
```

### 7.2 Fixed Inputs

```text
dataset hash
seed
temperature
top_k
budget
timeout
```

### 7.3 Outputs

```text
results.jsonl
summary.md
summary.csv
failure_cases.md
```

### 7.4 Fairness

```text
same input
same budget
same timeout
same evaluation script
plugin names hidden during blind review
```

---

## 8. Run Isolation and Security

### 8.1 Minimum Requirements

```text
Plugins do not write the DB directly
Plugins do not read the whole corpus directly
Plugins do not receive API keys directly
Plugins cannot run indefinitely
Plugin output must pass schema validation
```

### 8.2 Recommended

```text
subprocess / container
  ↓
JSON-RPC or HTTP
  ↓
scoped input
  ↓
timeout + memory limit + network off
```

### 8.3 Licensing

SciPal is AGPL-3.0-only.

Before integrating a plugin you must confirm:

- the plugin's license;
- whether commercial use is allowed;
- whether it is distributed over a network;
- whether it constitutes a derivative work.

Process isolation reduces coupling, but it does not replace a legal judgment.

---

## 9. Paper Plan

### 9.1 Positioning

Not "we integrated a few tools", but:

> a reproducible, plugin-based research-argument platform, plus a comparison of claim verification / retrieval / writing methods on that platform.

### 9.2 Contributions

```text
1. A port-based platform: contracts, manifest, runner, provenance
2. A unified evaluation protocol: same data/budget/metrics
3. Empirical comparisons across three ports
4. Failure modes and applicability boundaries
5. Reproducible artifacts
```

### 9.3 Experiment Table

| Port | Compared systems | Primary metrics |
|---|---|---|
| ClaimVerifier | LLM / rule / external | macro-F1, refute recall |
| Retriever | BM25 / dense / hybrid / rerank | Recall@10, MRR, nDCG |
| PaperGenerator | template / base / external | evidence coverage, unsupported rate |

### 9.4 Engineering-Application Article Structure

```text
Introduction
Related Work
System Design
Port Contracts
Evaluation Protocol
Experiments
Error Analysis
Limitations
Reproducibility
```

### 9.5 What We Cannot Claim

```text
We cannot claim "our method is SOTA"
unless the benchmark is large enough and statistical tests are included
```

### 9.6 Two Deliverables

```text
M4: Application Note preprint (1,500-4,000 words)
     publish first to establish priority and a citable version

M5: full engineering paper (later)
     expand the claim/query sets, add statistical tests and ablations
```

See Section 13 for the detailed Application Note plan.

---

## 10. Implementation Order and Milestones

### M0: Shared Infrastructure

```text
1. Define PortContract / PluginManifest / PluginRun
2. Create the plugins/ directory and the registry
3. Add the JSONL run log
4. Add the eval/plugin_bench.py skeleton
```

Acceptance:

```text
A dummy plugin runs end to end and its output passes schema validation
```

M0 implementation (pending merge):

```text
services/plugins/contracts.py
services/plugins/registry.py
services/plugins/runner.py
plugins/manifests/echo.yaml
plugins/ports/echo.json
plugins/adapters/echo.py
eval/plugin_bench.py
tests/test_plugin_infra.py
```

Validation:

```text
python eval/plugin_bench.py
cases=2 ok=2 failed=0
```

Trust model:

```text
M0 runs trusted local plugins in-process;
subprocess/container isolation belongs to a later stage.
```

### M1: Stage A (ClaimVerifierPort)

```text
1. Contract
2. Three adapters
3. 10-claim comparison
4. Report
```

M1 implementation (pending merge):

```text
services/plugins/claim_contracts.py
plugins/ports/claim_verifier.json
plugins/adapters/claim_verifier_nli.py
plugins/adapters/claim_verifier_rule.py
plugins/adapters/claim_verifier_underdetermines.py
plugins/manifests/claim_verifier_*.yaml
eval/plugins/claims_pilot_cases.json
eval/claim_verifier_bench.py
tests/test_claim_verifier_plugins.py
```

First-round results (10 claims / 11 evidence):

```text
claim-verifier-rule          accuracy 0.3636
claim-verifier-underdetermines accuracy 0.0000
majority baseline (supports)  accuracy 0.9091
```

Conclusion:

```text
The pipeline works;
the dataset is severely imbalanced (10 supports / 1 mentions);
these 11 items cannot support any "which algorithm is better" conclusion;
M1 only validates the contract and the comparison workflow.
```

The NLI adapter is wired in, but the default benchmark does not call an external
provider; it runs only with an explicit `--include-nli` and a configured LLM.

#### Stage A: Balanced Dataset (Derived)

To remove the label imbalance, add:

```text
scripts/build_claim_balanced_cases.py
eval/plugins/claims_pilot_balanced_cases.json
```

Construction:

```text
10 original claims
  × support (the original supporting evidence)
  × refute (an explicit negation of the claim + the same supporting evidence)
  × underdetermine (boundary/method sentences)
= 30 cases, 10/10/10
```

Results:

```text
claim-verifier-rule           accuracy 0.4333
claim-verifier-underdetermines accuracy 0.3333
majority baseline             accuracy 0.3333
```

Important limitations:

```text
refute cases are derived_opposite_claim, not new real clinical claims;
underdetermine reuses the 5 boundary evidence items;
derived refute labels must be human-reviewed before release.
```

These 30 cases can therefore be used for:

```text
port comparison, regression testing, method screening
```

They cannot be used for:

```text
claiming NLI generalization performance on clinical claims
```

### M2: Stage B (RetrieverPort)

```text
1. Contract
2. Five adapters
3. 100-query comparison
4. Report
```

M2 implementation (pending merge):

```text
services/plugins/retriever_contracts.py
plugins/ports/retriever.json
plugins/adapters/retriever_bm25.py
plugins/adapters/retriever_dense.py
plugins/adapters/retriever_hybrid.py
plugins/manifests/retriever_*.yaml
scripts/build_retriever_queries.py
eval/plugins/retriever_queries.json
eval/retriever_bench.py
tests/test_retriever_plugins.py
```

Hybrid results (74 queries / 100 papers, top_k=10):

| adapter | Recall@10 | MRR | nDCG@10 | latency |
|---|---:|---:|---:|---:|
| retriever-bm25 | 0.9459 | 0.8149 | 0.8476 | 539 ms |
| retriever-dense | 0.9324 | 0.8829 | 0.8954 | 979 ms |
| retriever-hybrid | 0.9459 | 0.9036 | 0.9142 | 742 ms |
| retriever-hybrid-rerank | 0.9865 | 0.9081 | 0.9280 | 1454 ms |

Data sources:

```text
14 seed_100 (HCC)
20 cross_topic (non-HCC)
20 claim-derived
20 paper-title
= 74 queries
corpus = 32 HCC + 20 cross-topic gold + 48 distractor = 100 papers
```

Found and fixed along the way:

```text
The hybrid adapter read paper_id from the top level,
but HybridSearch stores paper_id in metadata,
so paper_id came back empty and the hybrid metrics falsely dropped to 0.7778.
Restored after the fix; a regression test was added.
```

Important limitations:

```text
74 is still short of the 100-query target;
title queries are on the easy side;
cross_topic covers only a few topics;
no statistical significance conclusions can be drawn from this;
the next step should add harder/multi-hop queries.
```

An external retriever is not integrated yet; `external` is left for later.

### M3: Stage C (PaperGeneratorPort)

```text
1. Contract
2. Three adapters
3. 3-section comparison
4. Blind human evaluation
```

### M4: Application Note Preprint

```text
1. Consolidate the M0-M3 implementation and evaluation
2. Write a 1,500-4,000 word Application Note
3. Internal review and fact-checking
4. Publish the bioRxiv / arXiv preprint
```

### M5: Full Engineering Paper (Later)

```text
1. Expand the claim set and the query set
2. Add statistical tests and ablations
3. Consolidate the three experiment groups
4. Failure mode analysis
5. Artifact packaging
6. Submission
```

Dependencies:

```text
M0 → A → B → C → M4 (Application Note) → M5 (full paper)
```

Do not skip M0.

---

## 11. Stop Conditions for Each Step

```text
Stage A:
  If the three adapters cannot produce a unified output, stop and fix the
  contract first; do not expand to B.

Stage B:
  If the Recall@10 differences are within noise, stop; do not write
  "significant improvement".

Stage C:
  If assertion sentences cannot be reliably bound to evidence, stop and build
  the writing gate first.

Stage M4:
  If key metrics have no reproducible run, stop writing and first add
  run logs / data snapshots.
```

---

## 12. Current Recommendation

Execute in order:

```text
1. M0 shared infrastructure
2. A: ClaimVerifierPort
3. B: RetrieverPort
4. C: PaperGeneratorPort
5. M4: Application Note preprint
6. M5: full engineering paper (later)
```

---

## 13. Application Note Preprint Plan

> Once M0-M3 are complete, prioritize a 1,500-4,000 word Application Note preprint rather than going straight to a full research paper.

### 13.1 Positioning

An Application Note is not a "full research paper"; it answers:

```text
What problem does this software solve?
How is it used?
To what extent has it been validated?
Where can it be obtained?
What are its limitations?
```

It does not require:

```text
large-scale multicenter clinical validation
claims of a SOTA algorithm
complete theoretical novelty
```

### 13.2 Working Title

```text
SciPal: an evidence-grounded, plugin-ready workbench for
claim-level literature interrogation
```

Working title:

```text
SciPal: An Evidence-Driven, Pluggable Workbench for Claim-Level Literature Interrogation
```

### 13.3 Target Format

```text
Type: Application Note / Software Note
Preprint: bioRxiv or arXiv (cs.DL / q-bio)
Later submission targets: Bioinformatics Application Note,
         BMC Bioinformatics, GigaScience, F1000Research
```

Length:

```text
main text 1,500-4,000 words
abstract 150-250 words
3-5 figures
2-3 tables
30-50 references
```

> Exact limits depend on the target journal; check the Author Guidelines before submission.

### 13.4 Structure

```text
1. Motivation
   - Literature search is strong, but claim-level argumentation is weak
   - Generation tools are plentiful, but auditable evidence chains are missing
   - Plugins are plentiful, but there is no shared comparison platform

2. Software Design
   - L0-L4 data layers
   - Retrieval and the evidence envelope
   - Claim interrogation and human adjudication
   - writing brief
   - Plugin ports

3. Key Capabilities
   - Structured parsing and sentence-level provenance
   - Pro/con evidence retrieval
   - Claim state machine and event audit
   - Pluggable ports
   - Local deployment and multi-user isolation

4. Validation
   - 677 tests
   - The 100-question QA / SciFact / LitQA2 sets
   - A case study of 10 HCC claims
   - The OS counter-evidence case for claim_hcc_triple_os
   - Plugin A/B/C comparison (if already done)

5. Availability
   - GitHub / Gitee
   - AGPL-3.0-only
   - Docker Compose
   - Documentation and sample data
   - Zenodo DOI / release tag

6. Limitations
   - The claim set is still small
   - Online ingest is still limited
   - The writing gate is still brief + manual checks
   - SQLite single node
```

### 13.5 Evidence That Must Be Ready

Everything below must be in place before writing:

```text
1. A frozen release tag
2. The Docker image digest
3. The 677-test output
4. The 100-question QA result file
5. The SciFact / LitQA2 result files
6. Claim pilot data and adjudication records
7. Plugin A/B/C comparison results (at least A)
8. 3-5 key screenshots
9. Zenodo / institutional repository DOI
10. Author contributions and conflict-of-interest statement
```

Without these, do not start writing.

### 13.6 What We Must Not Write

```text
Do not write "first", "only", or "SOTA"
Do not write "clinically usable"
Do not write "replaces systematic reviews"
Do not report PFS as OS
Do not turn "no counterexample found" into "proven"
```

### 13.7 Writing Order

```text
1. Fix the figures and tables first
2. Then write Results / Validation
3. Then write Software Design
4. Then write Motivation
5. Write Abstract / Title last
6. Unify terminology and citations
7. Internal red-team review
8. Fact-check (every number has a run)
9. Publish the preprint
```

### 13.8 Schedule

```text
Week 1: figures and tables + evidence checklist
Week 2: first draft
Week 3: internal review + fact-checking
Week 4: polish + preprint release
```

### 13.9 Acceptance Criteria

```text
1. Main text of 1,500-4,000 words
2. Every performance number has a run_id / result file
3. Every claim example has an evidence_id
4. All figures are reproducible
5. Complete code and data availability statement
6. License and third-party dependency compliance
7. Passes internal red-team review
8. Preprint DOI is accessible
```

### 13.10 Risks

| Risk | Mitigation |
|---|---|
| Reviewers see it as "just engineering integration" | Emphasize port contracts, the evaluation protocol, and reproducibility |
| The claim set is too small | Frame it explicitly as a case study and make no generalization claims |
| Generation quality is subjective | Use evidence coverage / unsupported rate + blind human evaluation |
| AGPL licensing questions | State the license and the dependency boundaries clearly |
| The preprint gets scooped | Publish the preprint first and keep a version record |

### 13.11 How It Differs from the Full Paper

| Dimension | Application Note | Full paper |
|---|---|---|
| Length | 1,500-4,000 | 6,000+ |
| Focus | Software and usability | Methods and empirical results |
| Experiments | Case studies + small-scale comparison | Large-scale + statistical testing |
| Contribution | Tool and protocol | Algorithm/theory/system |
| Risk | Low | High |

---

The first step is M0 + A only; leave B/C alone.

Decide whether to continue after acceptance.
