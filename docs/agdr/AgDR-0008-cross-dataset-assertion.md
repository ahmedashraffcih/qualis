# cross_dataset_assertion: table-level aggregate comparison across two datasets

> In the context of validating AI-generated transformations (qualis#21), facing the need to catch silently dropped rows and shifted totals deterministically, I decided to add a `cross_dataset_assertion` check kind comparing one aggregate (`row_count` | `sum`) between the rule's dataset and a reference dataset within a Decimal tolerance, via a new optional adapter capability `check_aggregate`, to achieve in-database consistency assertions with bounded cost, accepting two separate aggregate queries per rule (each independently bounded by the statement timeout).

## Context

"The fact table should hold within 2% of staging's row count" is the assertion that catches the *consequence* of a bad (increasingly AI-written) transformation — regardless of what the transformation looks like. The design review (candidate A, AMBER) set two pre-build changes: defer `count_distinct` (hash-aggregate spill at high cardinality) and extend load-time identifier validation to every name that reaches SQL.

## Options Considered

| Option | Pros | Cons |
| --- | --- | --- |
| **Two independent aggregate queries (chosen)** | Reuses the one-connection-per-call adapter pattern; per-leg timeout; simple | Worst case 2× timeout wall-clock; not a point-in-time-consistent pair (documented) |
| Single JOIN/CTE query comparing both | One round trip, snapshot-consistent | Breaks the per-method pooling + READ ONLY scoping pattern; cross-schema JOIN complexity for zero practical gain at v1 |
| **Metrics `row_count` + `sum` only (chosen)** | O(n) single-pass scans, predictable at billions of rows | `count_distinct` deferred to a later opt-in |
| Include `count_distinct` | More expressive | Hash-aggregate spills temp disk at high cardinality; blows timeouts — review blocker |
| **Decimal comparison, tolerance as percent string (chosen)** | No float precision loss on `numeric` sums; YAML "2" / "0.5" parse exactly | Adapters must return values stringable into Decimal |
| Float comparison | Simpler | `sum` of a numeric column is Decimal in Postgres; float cast loses precision — review blocker class |

## Decision

- `CheckType.CROSS_DATASET_ASSERTION`; `CrossDatasetParams(metric, reference_dataset, reference_column=None, tolerance_pct="0")`. Target column for `sum` is the rule's own `column`; `reference_column` defaults to it.
- Load-time gate (trust boundary, same as AgDR-0005/0006): metric ∈ {`row_count`, `sum`}; `reference_dataset` (`table` or `schema.table`) parts + `reference_column` must fullmatch `[A-Za-z_][A-Za-z0-9_]*`; `tolerance_pct` must parse as a non-negative Decimal; `sum` requires a rule `column`.
- New optional capability `check_aggregate(schema, table, metric, column=None, condition=None) -> {"value": ...}` — hasattr-detected; adapters lacking it honesty-skip. SQL contract: `COALESCE(SUM("col"), 0)` (all-NULL sums compare as 0, never NULL) and a fixed metric→SQL map (no formatting of the metric name). Implemented for duckdb, postgres, sqlalchemy, in_memory.
- Engine semantics: reference `table_exists` probe first (detected, never guessed — AgDR-0006 precedent; probe failure = located skip). Decimal conversion with NaN/Infinity guard (non-finite aggregate = explicit fail, never compared). Zero-baseline convention from `drift._relative_change`: ref=0 ∧ target=0 → pass; ref=0 ∧ target≠0 → fail "baseline was zero"; else `|t−r|/|r| ≤ tolerance_pct/100`. Self-comparison (identical legs) logs a warning and proceeds. Table-level result: `violation_count ∈ {0,1}` (row_count precedent). The rule's `condition` applies to the **target** leg only.
- v1 scope: same database (cross-schema fine); cross-database documented unsupported.

## Consequences

- A transformation that drops 3% of rows fails a 2%-tolerance assertion regardless of how the SQL was written — the AI-era wedge
- Per-leg timeout means a worst case of 2× `statement_timeout_ms` per rule; the two legs are not a consistent snapshot (a concurrent load between legs can shift the comparison) — documented, acceptable for v1
- `count_distinct` lands later behind an explicit opt-in once cost is characterized
- Sibling adapters gain the check by implementing `check_aggregate` and inheriting the COALESCE + Decimal contract

## Artifacts

- Ticket: ahmedashraffcih/qualis#21 · Design review: ops repo `projects/qualis/design-reviews/2026-06-06-tariq-v060-perf-edge-case-pass.md` (candidate A)
- Foundations: AgDR-0005 (load-time trust boundary), AgDR-0006 (table_exists probe contract)
