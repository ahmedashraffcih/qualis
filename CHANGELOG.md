# Changelog

## v0.1.1 (2026-05-27)

- HTML scorecard report — single-file, traffic-light hero, DAMA dimension bars, drilldown table
- `qualis report` command — generate HTML or JSON reports to file
- PostgreSQL adapter with PG-dialect SQL templates (psycopg3, read-only transactions)
- `run_detailed()` on CheckRunner for detailed results with individual check outcomes
- `--fail-on-score` on report command for CI gating

## v0.1.0 (2026-05-26)

Initial release.

- 5 check types: not_null, unique, between, regex, sql
- DuckDB adapter built-in (CSV/Parquet support, zero-config)
- In-memory adapter for testing
- YAML-first rule definitions with typed parameters
- Template variables: `{{ today }}`, `{{ yesterday }}`, `{{ now }}`, `{{ env.VAR }}`
- DAMA DMBOK 2.0 — all 9 dimensions as first-class enums
- Weighted scoring with check-count normalization
- CLI: `qualis init`, `qualis validate`, `qualis check`
- Rich-colored console output with scorecard panel
- `--fail-on-score N` for CI pipeline gating
- `--allow-custom` security gate for Python check handlers
- `--output-format json` for machine-readable output
- Pydantic v2 settings with SecretStr credentials
- Typo suggestions on invalid enum values
- Apache 2.0 license
