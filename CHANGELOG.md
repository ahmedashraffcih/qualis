# Changelog

## v0.3.1 (2026-06-03)

First PyPI release — no behaviour changes from v0.3.0. Adds PyPI metadata
(classifiers, keywords, project URLs), the tag-driven release workflow with
OIDC trusted publishing, CI on Python 3.12/3.13, and contributor docs.

## v0.3.0 (2026-06-02) — Trust scaffolding

Informed by feedback from a live-delivery practitioner: "generation is the
commodity; grounding, control, and upkeep are the value." This release ships
the scaffolding that makes generated rules trustworthy.

- **Context model.** New `context.yaml` declares per-column sentinels
  (e.g. `0 = "unknown"`), exceptions, and business grain. `qualis discover
  --context` consults it and excludes declared sentinels from `in_set`
  suggestions. Closes the practitioner's #1 failure mode ("0 valid in some
  tables, invalid in others — generic check is wrong half the time").
- **Evidence trail.** `RuleSuggestion.rationale: str` is replaced with
  `evidence: SuggestionEvidence` — a structured snapshot of the profile that
  drove the suggestion (rows, nulls, distinct count, min/max, top values,
  sentinels consulted). The review screen surfaces this so reviewers see the
  reasoning. The old `.rationale` property still works for callers.
- **Review state machine.** Rules now carry `status: draft | needs_evidence
  | active | deprecated`. New `qualis review --pending` lists rules a
  reviewer sent back for SME confirmation. The discover review prompt adds
  `[B] Send back` as a first-class action that captures a reason.
- **Pluggable standards mapping.** `Rule.metadata` is an open dict; a new
  `RuleMetadataSchema` + `StandardsValidator` let programmes plug in their
  required-fields model (CDE, glossary, owner, frequency, threshold).
- **Referential-integrity check type.** New `check: reference_lookup` with
  `ReferenceLookupParams(reference, key_column)`. Implemented across
  in-memory, DuckDB, and PostgreSQL adapters (SQL pushdown on the latter
  two). New `ReferenceDataPort` plus `InMemoryReferenceData` adapter.
  Closes the practitioner's #3 failure mode ("wrong-key join passed every
  quality check because the rows existed; they were just the wrong rows").
- **Rule lineage fields.** `Rule` gains `version`, `supersedes`,
  `deprecated_at`, `approved_by`, and `metadata` — surfaced by the loader
  and writer when present.

Deferred to v0.4: PyPI publish, Snowflake / BigQuery adapters, `qualis
drift` (rule maintenance over time), live glossary integration.

## v0.2.2 (2026-05-31)

Trust-calibration patch — informed by a live-delivery practitioner's critique that
"a tool that generates confidently from thin context will produce rules that look
right but are wrong, at scale."

- **`in_set` confidence dropped from `high` to `medium`.** The heuristic observes
  values in the profiled dataset only; it cannot know the authoritative valid
  domain. Sentinels (e.g., `0` meaning "unknown") and rarely-occurring legitimate
  values are silently codified as "valid" today. Calling this "high confidence"
  was epistemically wrong.
- **Rationale now explicitly warns** to verify against the authoritative valid
  domain before accepting.

## v0.2.1 (2026-05-31)

Bug-fix release based on data-team testing (Anwar, Data Engineer).

- **`--rules` now accepts a file OR directory.** `qualis discover` writes a YAML file; the next step (`validate`/`check`/`report --rules <file>`) used to error "is not a directory." Fixed via new `load_rules_from_path()` that auto-detects.
- **`qualis init` scaffold runs first-try.** Old scaffold referenced `my_table`/`my_column` placeholders that crashed on `qualis check`. New scaffold creates `rules/completeness.yaml` + `data/example.csv` + three runnable rules. The "next steps" message gives the exact working command.
- **`qualis discover` success message points at the actual output path** (not `output.parent`).
- **`qualis discover` sets `severity: critical`** for `not_null` and `unique` rules on ID-like columns. Previously every suggestion was `warning`.

## v0.2.0 (2026-05-30)

**Featured commands:** `qualis diff` (score comparison), `qualis discover` (rule suggestion), `qualis-github-action`.

- **`qualis diff`** — compare quality scores between two runs with trend arrows; `--fail-on-regression` for CI gates
- **`qualis discover`** — statistical profiler + heuristic rule suggester; interactive `git add -p` style review; pure deterministic (no LLM API key required)
- **GitHub Action** — composite action posts a sticky PR comment with the scorecard; uploads the HTML report as an artifact
- **3 new check types**: `in_set`, `row_count`, `not_negative` across DuckDB and PostgreSQL adapters
- **PostgreSQL adapter** check methods extended for all 8 check types
- Reports loader (`load_report`) reconstructs a `DatasetScore` from a JSON report file
- `run_detailed()` on `CheckRunner` returns both `DatasetScore` and `list[CheckResult]`

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
