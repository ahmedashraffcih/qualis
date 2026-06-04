# Violation sampling as an optional adapter capability

> In the context of attaching real failing-row evidence to violations (`--sample-rows`), facing the constraint that `DatabasePort` cannot grow required methods without breaking the published sibling adapters, I decided to expose sampling as an optional `fetch_violation_samples` capability discovered via `hasattr`, to achieve evidence on capable adapters with zero protocol break, accepting that sampling silently degrades to the placeholder on adapters without it.

## Context

PR #3 made `CheckResult.violations` a bounded sample holding one placeholder (no row data reaches the engine — adapters return count dicts). Ticket #8 adds real evidence. `qualis-snowflake` and `qualis-bigquery` (v0.1.0, on PyPI) implement the current `DatabasePort` protocol; any new required method forces releases of both. The codebase already has one optional-capability precedent: `check_reference_lookup` pushdown, feature-detected at `rule_engine.py` via `hasattr`.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Optional capability via hasattr** | Zero protocol break; siblings conform unchanged; follows existing precedent; engine has one fallback path (the placeholder) | Capability invisible to type checkers; per-adapter duplication of failing-row predicates |
| New required `DatabasePort` method | Type-checked everywhere | Breaks both sibling packages; forces coordinated releases for an evidence feature |
| CLI-side re-query (no engine change) | Engine untouched | Duplicates check semantics outside the domain; loses redaction integration; per-engine SQL leaks into the CLI layer |

## Decision

Chosen: **optional capability**, signature `fetch_violation_samples(schema, table, column, kind, params, limit) -> list[{"record_id", "actual_value"}]`. The engine's `_sample` upgrades to real rows only when sampling was requested AND the check passes a `kind` AND the adapter has the method; every other path — including a sampling exception, which is logged at WARNING — yields the existing placeholder. Predicates in each adapter mirror that adapter's own count templates so sampled rows are always members of the counted set. Row identity: `ctid` (Postgres), 1-based `row_number()` (DuckDB — works on registered CSV/parquet views), list index (in-memory).

## Consequences

- Sampling is evidence, never correctness: `violation_count` and `passed` are computed before and independently of sampling
- For `unique`, evidence shows members of duplicate groups while the count is "extra copies" — sampled size may exceed the count for the same rule; documented in the capability docstring
- Sibling adapters gain sampling whenever they add the method — no core release needed
- `--sample-rows` is capped at `MAX_SAMPLE_VIOLATIONS` (100) at both the CLI (typer max) and engine (min) layers

## Artifacts

- Ticket: ahmedashraffcih/qualis#2 → #8 (PR pending)
- Related: AgDR-0001 (bounded violation sample — the container this fills)
