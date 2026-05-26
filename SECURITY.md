# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities through
[GitHub Security Advisories](https://github.com/ahmedashraffcih/qualis/security/advisories/new).

Do **not** open a public issue for a security vulnerability.  We will
acknowledge your report within 72 hours and aim to release a fix within
14 days for critical issues.

## Security model

Qualis is a **local-first, offline-capable** data quality framework.

- Rules are loaded from YAML files on disk — no remote rule fetching.
- Data never leaves the machine unless you configure an external adapter.
- The `redact_actual_value` setting (`QUALIS_REDACT_ACTUAL_VALUE=true`) removes
  sensitive field values from violation reports before they reach any output.
- No secrets are stored by Qualis.  Database credentials must be supplied via
  environment variables (e.g. `QUALIS_DATABASE_URL`).
- The `sql` check type executes arbitrary SQL against your configured adapter.
  Restrict rule-file access to trusted authors to prevent SQL injection through
  rules.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
