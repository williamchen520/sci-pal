# Work Plan: Discipline-Agnostic Core, Domain Packs, and Distribution

> Status: Pending review  
> Positioning: Aimed at developers building on SciPal who have a CS background, campus/institute computing centers, and open-source distribution.  
> Principles: The core is discipline-agnostic; domain knowledge is mounted as domain packs; declarative first, with Python hooks as the fallback.

## 1. Background

SciPal still contains HCC/biomedicine hardcoding:

- Domain taxonomy;
- Section types;
- QA/review/brief prompts;
- Vocabularies;
- Evaluation sets;
- UI terminology.

The goal is not to build "an admin panel for non-technical users" but to enable:

```
a developer does not touch the core
→ writes a domain pack
→ signs it
→ distributes it
→ deploys it to a new institution or discipline
```

## 2. Target Users

1. Domain researchers with Python skills;
2. University/institute computing centers;
3. Teams doing secondary development;
4. Labs/supercomputing centers that need offline deployment.

## 3. Non-Goals

- No-code configuration for non-technical PIs;
- Arbitrary users installing plugins;
- A stable API guarantee;
- A public plugin marketplace;
- A visual pack editor in v1.

## 4. Core Architecture

```
scipal-core          discipline-agnostic
├─ VFS / permissions
├─ retrieval / evidence / citations
├─ tasks / audit
└─ SDK extension points

scipal-sdk           developer API
├─ DomainPack
├─ TaxonomyProvider
├─ SectionClassifier
├─ EvidenceSchema
├─ PromptProvider
├─ SourceConnector
└─ Evaluator

packs/               domain packs
├─ biomed-hcc
├─ chemistry
└─ ...
```

The core depends only on the SDK and never imports a specific domain pack.

## 5. Domain Pack Granularity

Three levels:

```
discipline      chem
subfield        chem.organic
research group  chem.organic.lab-x
```

Rules:

- Pack IDs are dot-separated;
- `extends` inherits from a parent pack;
- `compose` combines multiple packs;
- A workspace selects its primary pack;
- A paper can belong to multiple packs;
- Research-group packs may override prompts/vocabularies but cannot change core permissions.

Example:

```yaml
id: chem.organic.lab-x
version: 0.1.0
extends: chem.organic
```

## 6. Pack Directory Structure

```text
packs/chemistry/
├─ pack.yaml
├─ taxonomy.yaml
├─ section_types.yaml
├─ evidence_schema.yaml
├─ sources.yaml
├─ prompts/
│  ├─ qa.md
│  ├─ review.md
│  └─ brief.md
├─ hooks/
│  └─ hooks.py
├─ ui/
│  └─ labels.zh.yaml
├─ eval/
│  └─ gold.jsonl
├─ tests/
│  └─ test_pack.py
├─ LICENSE
└─ README.md
```

## 7. pack.yaml

```yaml
id: chemistry
version: 0.1.0
discipline: chemistry
language: zh
license: AGPL-3.0-only
extends: null
requires:
  scipal_sdk: ">=0.1"
hooks:
  section_classifier: hooks.hooks:ChemistrySectionClassifier
  evidence_schema: hooks.hooks:ChemistryEvidenceSchema
```

Notes:

- `scipal_sdk` is only a hint; it is not a compatibility guarantee;
- The core commit is recorded at install time;
- Breaking changes are called out in the release notes.

## 8. Declarative Configuration + Python Hooks

### Declarative
- taxonomy;
- section types;
- evidence fields;
- prompt;
- sources;
- UI labels;
- eval gold.

### Python Hooks
- Complex section classification;
- Custom evidence extraction;
- Custom evaluation;
- Specialized data sources.

Constraints:

- Hooks can access data only through the SDK context;
- No direct database connections;
- Cannot read `/etc` or other workspaces;
- Run in a controlled process;
- Packs must be signed.

## 9. SDK Extension Points

Start with this minimal set:

```python
class TaxonomyProvider(Protocol):
    def classify(self, text: str) -> list[TaxonomyLabel]: ...

class SectionClassifier(Protocol):
    def classify(self, title: str, path: list[str]) -> str: ...

class EvidenceSchema(Protocol):
    def validate(self, evidence: dict) -> list[str]: ...

class PromptProvider(Protocol):
    def get(self, name: str, language: str) -> str: ...

class SourceConnector(Protocol):
    def search(self, query: str, **kwargs) -> list[SourceItem]: ...

class Evaluator(Protocol):
    def evaluate(self, gold: list[dict], answers: list[dict]) -> dict: ...
```

No stable API guarantee, but:

- SDK version numbers;
- Changelog;
- Migration guide;
- Example packs updated alongside.

## 10. Removing Hardcoding from the Core

First migration batch:

| Current | Moves to |
|---|---|
| `domain_taxonomy.py` | `packs/biomed-hcc/taxonomy.yaml` |
| `section_types.py` | `section_types.yaml` |
| QA prompt | `prompts/qa.md` |
| review prompt | `prompts/review.md` |
| brief prompt | `prompts/brief.md` |
| Domain vocabulary | `taxonomy.yaml` |
| Eval gold | `eval/gold.jsonl` |

Acceptance:

```bash
grep -R "HCC\|hepatocellular\|ORR" scipal/ --include=*.py
```

Domain terms should not appear in the core code.

## 11. Git Distribution

### Repository

```text
scipal-packs/
├─ packs/
│  ├─ biomed-hcc/
│  ├─ chemistry/
│  └─ general/
├─ keys/
│  └─ allowed_signers
└─ README.md
```

### Versioning

- semver recommended;
- Tags: `chemistry-v0.1.0`;
- Installs pin a commit/tag;
- No floating branches.

### Signing

Signing is required:

- minisign / Ed25519;
- Each pack produces `pack.tar.gz.minisig`;
- Verified at install time;
- Public keys live in `keys/allowed_signers`;
- Unsigned packs are rejected by default.

### Installation

```bash
scipal pack install git+https://.../scipal-packs.git#chemistry-v0.1.0
```

Or:

```bash
scipal pack install chemistry-0.1.0.tar.gz
```

## 12. Pack Validation

```bash
scipal pack validate packs/chemistry
scipal pack test packs/chemistry
```

Checks:

- manifest schema;
- Inheritance;
- taxonomy;
- Section samples;
- evidence schema;
- Prompt rendering;
- Hook imports;
- eval smoke;
- Signing.

## 13. Extension Documentation

```text
docs/extending/
├─ quickstart.md
├─ pack-spec.md
├─ sdk-api.md
├─ prompts.md
├─ evidence-schema.md
├─ hooks.md
├─ testing.md
├─ signing.md
├─ distribution.md
├─ offline-bundle.md
└─ examples/
   ├─ chemistry/
   └─ general/
```

Requirements:

- Each page can be followed end to end on its own;
- Has a minimal example;
- Has troubleshooting;
- Has upgrade notes.

## 14. Non-Medical Pilot

Suggested first non-medical pack: **chemistry**.

Why:

- Clearly different structure;
- Plenty of open data;
- Shares some terminology with biomedicine, but sections/evidence differ;
- Good for validating the core abstractions.

Acceptance:

```
Install the chemistry pack
→ with no core code changes
→ 20-question smoke test
→ retrieval/evidence/citations work
```

## 15. Distribution Formats

### Docker

```text
scipal-core:<version>
scipal-lab:<version>
scipal-institute:<version>
```

Mount packs:

```bash
-v ./packs:/etc/scipal/packs
```

### Source

```bash
git clone
pip install -e .
scipal pack install ...
```

### Offline bundle

```text
scipal-offline-<version>.tar.gz
├─ images/
├─ packs/
├─ compose.yml
├─ install.sh
├─ checksums.txt
└─ signatures/
```

Contents:

- Docker images (`docker save`);
- Domain packs;
- Configuration templates;
- Install script;
- Checksums;
- Signatures.

Model weights:

- Not bundled by default;
- Optional via `--with-models`;
- Verified separately;
- License ships with the bundle.

## 16. Offline Bundle After Deep DSH Integration

Future goal:

```
SciPal + DSH + domain packs + local models
→ a single offline installer
```

Requirements:

- No internet dependency;
- Intranet model endpoints are swappable;
- Domain packs are pluggable;
- Idempotent install script;
- Upgrade/rollback;
- License inventory.

## 17. Licensing

Core: AGPL-3.0-only.

Domain packs: AGPL-3.0-only.

Requirements:

- `LICENSE` ships with each pack;
- `pack.yaml` declares the license;
- Docs explain AGPL obligations;
- Source obligations for developers distributing modified versions;
- Closed-source integration boundaries stated clearly.

## 18. Security

- Only admins may install packs;
- Signature verification;
- Packs cannot connect to the DB directly;
- Packs cannot cross workspaces;
- Packs cannot read system configuration;
- Hooks run in a controlled process;
- Prompt-injection testing;
- Install/upgrade audit.

## 19. Versioning and Compatibility

No stable API guarantee, but we provide:

- `scipal_sdk` version;
- Recorded core commit;
- Pack lock;
- Release notes;
- Migration guide;
- Conformance tests.

At install time:

```
warn if pack requires newer sdk
fail if pack uses removed API
```

Old packs are not guaranteed to work forever.

## 20. Phases

### P0: SDK and Loader
- Define extension points;
- pack manifest;
- Validator;
- Directory layout;
- Minimal example.

### P1: Pack-ify HCC
- Extract taxonomy/section/prompt;
- Remove hardcoding from the core;
- HCC becomes `biomed-hcc`;
- Regression tests.

### P2: CLI and Signing
- `scipal pack new/validate/test/build/install`;
- Signing/verification;
- Git installs;
- Lock files.

### P3: Chemistry Pilot
- Create the `chemistry` pack;
- 20-question smoke test;
- Documentation;
- No core changes.

### P4: Offline Bundle
- Docker save;
- compose;
- install.sh;
- checksums/signatures;
- Placeholder for DSH integration.

## 21. Acceptance

- Core code has no hardcoded HCC/ORR or similar terms;
- New packs need no core changes;
- Unsigned packs are rejected at install;
- Signed packs install offline;
- `scipal pack test` runs;
- Chemistry 20-question smoke test;
- Documented quickstart reproduces;
- All AGPL files present.

## 22. Risks

- No stable API guarantee leads to pack fragmentation;
- Hook security boundaries;
- Signing key management;
- Pack/core version drift;
- Offline bundle too large;
- Model licenses;
- Uneven domain pack quality;
- Implicit discipline assumptions remain in the core.

## 23. Open Questions

1. Signing tool: minisign or cosign?
2. Should the pack repository be a separate git repo?
3. Which data sources for the chemistry pilot?
4. Should the offline bundle include model weights?
5. Should pack authors be required to provide a 20-question smoke test?
6. Is pack installation restricted to admins?
7. Should the `general` pack be kept as a fallback?

## 24. Recommendation

```
Core + SDK + declarative/Python hybrid
+ three-level domain packs
+ Git + signing
+ AGPL-3.0
+ chemistry pilot
+ offline bundle
+ no stable API guarantee, but migration and conformance support
```
