# SQLAlchemy meta-adapter via Core expressions + entry-point adapter registry

> In the context of reaching ~20 database engines without hand-writing an adapter per engine, facing a hardcoded 3-way if-elif in `bootstrap.py` and no plugin mechanism, I decided to add a generic entry-point registry (`qualis.adapters` group, group-agnostic loader) and a SQLAlchemy meta-adapter built on Core expressions, to achieve engine reach plus a reusable dialect abstraction for the upcoming condition-pushdown redesign, accepting a pinned `sqlalchemy>=2.0,<3` optional dependency and dialect-dependent feature gaps (regex, timeouts) documented honestly.

## Context

`bootstrap.py:24-38` selects adapters with a hardcoded if-elif; `QualisSettings.adapter` is a closed `Literal`. Sibling packages (qualis-snowflake, qualis-bigquery) are selected manually. The v0.5.0 spec (item 7) calls for a `qualis.adapters` entry-point registry + SQLAlchemy meta-adapter; the Solution Architect's pre-Build review (2026-06-05, APPROVE-WITH-CONDITIONS) binds four conditions: C1 generic `_load_entry_points(group, protocol)` reusable for a future `qualis.catalogs` group; C2 drivers user-supplied; C3 SQLAlchemy **Core expressions**, not per-dialect raw SQL; C4 a per-adapter timeout-honesty matrix.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Core expressions + generic registry (chosen)** | Injection-safe by construction; one implementation, many dialects; the expression layer doubles as the dialect abstraction PR 3's condition redesign needs; registry generic → catalogs reuse free | Dialect feature gaps (regex, FILTER) need explicit handling; `sqlalchemy` dep (optional extra) |
| Per-dialect raw-SQL templates inside one adapter | Mirrors existing duckdb/postgres template style | N template sets to maintain ≈ N hand-written adapters with extra steps; re-opens string-interpolation surface; rejected by review condition C3 |
| Keep manual selection, ship more sibling adapters | No core changes | Linear cost per engine; doesn't produce the dialect abstraction; leaves bootstrap hardcoded |

## Decision

- **Registry**: `src/qualis/plugins.py` exposes `load_entry_points(group, protocol)` — group-agnostic, validates loaded objects against the protocol's public surface, returns `{name: factory}`. `bootstrap.py` resolves `settings.adapter` against built-ins first, then entry points; unknown names fail with the full list of known names. `QualisSettings.adapter` widens `Literal → str` (validation moves to resolution time, where the registry knows the real name set).
- **Factory contract**: an entry point resolves to a callable invoked as `factory(settings)` returning a `DatabasePort` implementation. qualis itself registers `sqlalchemy` through its own entry point — the mechanism is proven end-to-end by the package's own packaging, not just by mocks.
- **Adapter**: `qualis.adapters.sqlalchemy` (guarded import, `qualis[sqlalchemy]` extra, pin `>=2.0,<3`). All checks via Core expressions (`func.sum(case(...))` over `FILTER` for dialect reach); duplicate-count semantics = `count(col) − count(distinct col)` (extra copies, matching the in-memory adapter); `fetch_violation_samples` via Core predicates + `row_number()`. SQLite lacks a native `REGEXP` function — the adapter installs a Python `regexp()` on connect for the sqlite dialect only (honest enablement, not emulation elsewhere).
- **Timeouts**: NOT implemented in the meta-adapter v1 — support is dialect-specific and faking it violates the timeout guard's purpose. A timeout-honesty matrix lands in `docs/adapters.md`.

## Consequences

- Sibling adapters can migrate to entry-point registration without core releases; the same loader serves `qualis.catalogs` (Purview-era) unchanged
- PR 3's condition redesign gains a portable expression layer to target instead of raw SQL strings
- Engines whose dialect lacks regex support surface a clear unsupported error on `regex` checks rather than silently passing
- `settings.adapter` typo errors move from pydantic validation to bootstrap resolution — error message must stay first-class

## Artifacts

- Ticket: ahmedashraffcih/qualis#10
- Design review binding C1–C4: ops repo `projects/qualis/design-reviews/2026-06-05-tariq-v050-pr3-pr4-review.md`
- Related: AgDR-0003 (sampling capability the meta-adapter also implements)
