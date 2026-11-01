# Contributing to SciPal

**English** | [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for your interest in SciPal. We welcome bug reports, design feedback, documentation fixes, and focused pull requests.

**Please open an issue before you start coding.** This lets us confirm the problem, agree on scope, and avoid duplicate work. Pull requests that were not discussed in an issue may be closed without review.

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
