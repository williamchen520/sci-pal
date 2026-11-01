# Security Policy

## Supported Versions

SciPal is under active development. There is no stable release yet.

| Version | Supported |
|---|---|
| `dev` / `main` (development) | Best effort |
| Tagged releases | None yet |

Security fixes are applied to the active development branch first. Because the project is a work in progress, older snapshots and forks are not supported.

## Reporting a Vulnerability

**Do not open a public GitHub issue, discussion, or pull request for a security vulnerability.**

Report it privately by email to:

```text
chenwei-ucas@outlook.com
```

Please include:

- A short description of the issue and its impact.
- Affected version, commit, or branch.
- Reproduction steps or a proof of concept.
- Any relevant logs, configuration, or environment details.
- Whether the issue has been disclosed elsewhere.

Do not include real credentials, private keys, personal data, or unpublished research data in the report. Use redacted examples.

## What to Expect

- We aim to acknowledge a report within **3 business days**.
- We will investigate and may ask for clarification or a minimal reproduction.
- We will keep you informed about remediation progress when practical.
- We will credit reporters in the fix if they want attribution.
- Please give us reasonable time to investigate and release a fix before public disclosure.

These are best-effort targets for a small, development-stage project, not a contractual service-level agreement.

## Scope

Examples of in-scope issues:

- Authentication or session handling flaws.
- Authorization bypass or cross-workspace data leakage.
- SQL injection, command injection, or unsafe deserialization.
- Path traversal or arbitrary file read/write.
- Leakage of API keys, database credentials, or private paper content.
- Prompt-injection paths that can cause unauthorized tool use or data exfiltration.
- Vulnerabilities in the ingestion, parsing, retrieval, or evidence pipeline that could corrupt provenance.

Out of scope:

- Bugs that require a already-compromised host or administrator account.
- Denial-of-service reports based only on unrealistic resource consumption.
- Missing security headers without a demonstrated impact.
- Reports about third-party services that are not controlled by this project.
- Social engineering or physical attacks.

## Safe Harbor

We will not pursue legal action against researchers who:

- Make a good-faith effort to avoid privacy violations, data destruction, and service disruption.
- Test only against their own local deployment or data.
- Report the issue privately and give us time to respond.
- Do not exploit the issue beyond what is needed to demonstrate it.

## Secrets and Credentials

If you accidentally commit a secret, rotate it immediately and notify the maintainer. Do not paste the secret into a public issue. The repository must not contain:

- `.env` files
- Database dumps
- API keys or access tokens
- Session cookies
- Private keys
- Production connection strings

## Dependency Reports

If a dependency has a known vulnerability, include the package name, affected version range, and the relevant advisory. We will assess whether the dependency is reachable in SciPal's runtime.

## Contact

Security contact: **chenwei-ucas@outlook.com**
