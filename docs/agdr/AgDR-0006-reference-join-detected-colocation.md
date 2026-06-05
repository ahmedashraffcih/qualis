# Reference-JOIN pushdown with detected co-location; fallback removal

> In the context of reference_lookup at production scale, facing the rejected same-DB assumption (Solution Architect finding B4: reference data arrives via a separate `ReferenceDataPort` — file/HTTP/in-memory — so co-location is false-by-architecture) and the engine's unbounded full-column Python fallback, I decided to make JOIN pushdown an explicitly **detected** path (author opts in via `reference_schema`; the adapter's `table_exists` probe confirms; otherwise the existing valid_values path runs) and to replace the full-column fallback with an honesty skip, to achieve in-database membership validation without materializing reference sets, accepting one `table_exists` probe per JOIN-eligible rule evaluation.

## Context

`check_reference_lookup` today loads ALL reference values through `ReferenceDataPort` into Python and ships them back as SQL literals/binds — fine for hundreds of codes, wrong for million-row reference tables that already live in the checked database. The engine also carries a fallback that `SELECT`s the entire target column into Python when an adapter lacks the pushdown method — a worst-case memory profile guarding a path no shipped adapter uses (all four core adapters + both siblings implement `check_reference_lookup`).

## Options Considered

| Option | Pros | Cons |
| --- | --- | --- |
| Assume same-DB when `reference` matches a table name | No params change | Guessing: a logical reference name colliding with a table silently changes semantics — B4's exact objection |
| **Author opt-in (`reference_schema`) + adapter probe (`table_exists`) (chosen)** | Intent is explicit; the probe verifies reality; absent table degrades loudly to the values path | New optional param; one probe query per evaluation |
| Always materialize (status quo) | Simple | O(reference-size) memory + SQL size; the scale hole stays open |
| Keep the full-column fallback | Works with any adapter | Unbounded memory; dead code in practice; violates the honesty pattern established by AgDR-0005 |

## Decision

- `ReferenceLookupParams.reference_schema: str | None = None` — set ⇒ "the reference is a table in the checked database at `reference_schema.reference`". Unset ⇒ exactly today's behavior.
- Engine flow when set: adapter exposes optional capability `check_reference_join` AND `adapter.table_exists(reference_schema, reference)` ⇒ JOIN pushdown. Probe fails ⇒ **skipped** with a located reason ("reference table X not found in the checked database") — detected, never guessed; falling back to the values path silently would mask a misconfiguration.
- JOIN shape (implemented for duckdb / postgres / sqlalchemy): **`NOT EXISTS` correlated subquery, not `NOT IN`** — `t.col IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ref r WHERE r.key = t.col)`. Pre-Build review condition **C1**: `NOT IN (subquery)` evaluates to NULL for every row the instant the subquery yields one NULL key, silently zeroing invalid counts; `NOT EXISTS` is NULL-safe by construction. This is a **contract on the `check_reference_join` capability** so sibling implementations inherit it. Target aliased `t`, reference confined to the correlated subquery — the outer query's FROM contains only `t`, so unqualified rule-`condition` columns bind to `t` structurally (review condition **C2**: the namespace mechanism is single-table outer scope, not identifier rewriting). Reference identifiers travel through double-quoted rendering, never raw format (condition **C4**). in_memory: N/A — its reference data IS the port; values path remains.
- The engine's full-column Python fallback is **removed**: adapters lacking `check_reference_lookup` now yield `skipped` ("adapter does not implement reference_lookup") — same honesty shape as conditioned-rule skips.

## Consequences

- Million-row reference tables validate in-database with zero Python materialization
- A typo'd `reference_schema` surfaces as a visible skip, not a silent semantics change
- Sampling for JOIN-mode violations reuses the same NOT IN subquery predicate, so evidence ⊆ counted set holds
- Sibling adapters: untouched; they gain JOIN mode whenever they add the capability (inheriting the NULL-safe NOT EXISTS contract)
- Behavior change (condition **C3**): out-of-tree adapters that omit `check_reference_lookup` previously hit the slow full-column values diff; they now honesty-skip with a reason — release notes call this out
- Regression proofs required by review: a nullable-reference-key test (C1) and a condition column whose name also exists in the reference table (C2)

## Artifacts

- Ticket: ahmedashraffcih/qualis#14 · Design review B4: ops repo `projects/qualis/design-reviews/2026-06-05-tariq-v050-pr3-pr4-review.md`
- Foundations: AgDR-0004 (Core layer), AgDR-0005 (condition composition, honesty pattern)
