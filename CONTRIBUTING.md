# Contributing to SciPal

**English** | [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for your interest in SciPal. We welcome bug reports, design feedback, documentation fixes, and focused pull requests.

**Please open an issue before you start coding.** This lets us confirm the problem, agree on scope, and avoid duplicate work. Pull requests that were not discussed in an issue may be closed without review.

## Architecture Constitution (Highest Safety Rule)

`ARCHITECTURE.json` is the system constitution and is **read-only for AI**.

To change a route, the AI must:

1. output the proposed JSON block and rationale in chat;
2. wait for the human to reply **“批准修改”**;
3. only then edit `ARCHITECTURE.json`; mark new nodes `"status": "planned"`;
4. run `python scripts/validate_arch.py`;
5. then write the Flask route/handler, and validate again.

If a test fails because Python disagrees with the JSON contract, fix Python; **never reverse-edit JSON parameters to make tests pass**.

Commits that modify `ARCHITECTURE.json` must include `[APPROVED_BY_HUMAN]` in the commit message. The `pre-commit` + `commit-msg` hooks enforce this.

Wild routes that are absent from the JSON are rejected. See [docs/开发流程规范.md](docs/开发流程规范.md).

## Autonomous Build and PR Approval

Default workflow: propose JSON change if needed → implement → run `validate_arch.py` → run the full test suite → write a worklog → open a PR.

- Fix failures yourself and rerun until the suite is green.
- Stop only for an unsolvable loop, unapproved JSON changes, core auth/tenancy changes, irreversible data operations, research decisions, or a >300-line refactor.
- Write `worklogs/YYYY-MM-DD-<topic>.md` and include modules, business-logic changes, test pass rate, and external-API/data risks.
- PRs are opened as `Pending Review`. **Do not merge until a human replies exactly “批准合并”.**
- PRs with more than 300 net changed lines must be marked `[LARGE]` and require dedicated review.

## Before You Start

- Read the [README](README.md) and the [architecture overview](docs/en/Architecture-Overview.md).
- Search existing issues and pull requests first.
- For a bug report, include a minimal reproduction, the expected result, the actual result, and your environment (OS, Python version, database backend, model provider).
- For a feature request, describe the problem and the proposed behavior before proposing an implementation.

## Development Setup

```powershell
python -m venv venv_sciPal_py312
venv_sciPal_py312\Scripts\pip install -r requirements.txt
venv_sciPal_py312\Scripts\python.exe api_server.py
```

Run the test suite from the repository root:

```powershell
venv_sciPal_py312\Scripts\python.exe scripts\run_tests_guarded.py
```

The standard unittest command is also accepted:

```powershell
venv_sciPal_py312\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

A pull request must pass the unit tests before it can be merged. If a test is flaky, explain why in the pull request rather than deleting or skipping it.

## Pull Request Rules

1. **One pull request, one topic.** Do not mix refactors, features, and unrelated formatting changes.
2. **Link the issue.** The pull request description must reference the issue it resolves.
3. **Keep the tests green.** Add or update tests for behavior changes.
4. **Follow the PR template.** Every pull request must include the required sections from `.github/pull_request_template.md`, including the benchmark/evidence section. CI enforces this.
5. **Do not hardcode paths.** Use `pathlib.Path` and repository-relative paths. Do not commit machine-specific absolute paths, credentials, `.env` files, or database dumps.
6. **Preserve provenance.** Changes to retrieval, parsing, evidence, claims, or database write paths must explain how traceability is preserved.
7. **Do not rewrite unrelated code.** Small, reviewable diffs are merged faster.
8. **Update documentation.** If you change a public API, configuration variable, route, schema, or workflow, update the relevant Markdown documentation.
9. **Be precise about data changes.** Database migrations must be idempotent and must include a rollback or verification plan.
10. **Respect the license.** Contributions are accepted under AGPL-3.0-only.

## Commit Messages

Use a short, imperative subject line. For example:

```text
fix: return 404 when a paper has no parsed sections
feat: add sentence-level source locators
docs: clarify PostgreSQL benchmark policy
```

Include a body when the reason for the change is not obvious. Reference the issue with `Refs #123` or `Fixes #123`.

## Code Style

- Python 3.12, standard library where practical.
- Prefer small functions with explicit inputs and outputs.
- Keep SQL parameterized; never interpolate user input into SQL.
- Keep retrieval and evidence logic deterministic and testable.
- Do not commit secrets, session cookies, private keys, or production connection strings.
- Follow the existing module boundaries; do not introduce a new abstraction without a concrete use case.

## Documentation and Translation

- Markdown documentation may be written in Chinese or English.
- Do not translate comments inside `.py` files as part of documentation work; keep code and comments in their original language.
- English documentation should use North American spelling and standard technical terms.
- When you add a document, link it from the relevant index (`README.md` or `docs/README.md`).

## Review Process

A maintainer will review the pull request after the tests pass. Expect questions about scope, edge cases, and data provenance. Address review comments in new commits rather than force-pushing over the review history.

## Security

Do **not** report security vulnerabilities in a public issue. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contribution is licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only). See [LICENSE](LICENSE).

---

## Current Data Isolation and Governance (2026-11-12)

### Two databases

```text
scipal_core      users / auth / projects / experiments / notes / tasks
scipal_rebuild   papers / paragraphs / sentences / vectors
```

Rules:

```text
no cross-database foreign keys
logical IDs only
routes must use core_connection() or corpus_connection()
business reads never hit scipal_rebuild
corpus reads never hit scipal_core
```

### Least privilege and migrations

```text
core_app          business/auth, no DDL
corpus_reader     corpus read only
corpus_writer     corpus write, no DDL
app startup       must not CREATE/ALTER tables
plugin schema     scripts/migrate_ingest_tracking.py (owner role)
```

### Production environment guard

```text
SCIPAL_ENV=production
reject loopback/wrong-database DSNs
require SCIPAL_CORE_DSN and SCIPAL_PG_CORPUS_DSN
```

### Governance gate

```powershell
python scripts/governance_gate.py --paths <changed> --ops <ops> --plan "..." --risk "..."
```

A blocked change requires a human “批准执行” and the `governance-approved` PR label.
CI uses the base branch's gate script, so a PR cannot weaken the gate it is judged by.

### Required checks

```text
python scripts/validate_arch.py
python scripts/check_data_boundary.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/smoke_http.py          # 27/27
python scripts/smoke_group_b.py       # 13/13
```

### Backups

```text
core 6h / 7d; corpus 7d / 28d
encrypted; restore drill includes GIN + HNSW
```
