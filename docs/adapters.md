# Adapters

How qualis reaches your database, and what each adapter honestly supports.

## Resolution

`QualisSettings.adapter` (env: `QUALIS_ADAPTER`) names the adapter. Built-ins
resolve first; anything else is looked up in the `qualis.adapters`
entry-point group, where third-party packages register a factory invoked as
`factory(settings)`:

```toml
[project.entry-points."qualis.adapters"]
myengine = "my_package:create_adapter"
```

Built-ins always win over a same-named entry point — a third-party package
cannot shadow `postgres`. Unknown names fail with the full list of known
adapters. qualis's own `sqlalchemy` adapter registers through this exact
mechanism (see AgDR-0004), so the plugin path is exercised by the package
itself.

## The SQLAlchemy meta-adapter

```bash
pip install 'qualis[sqlalchemy]'   # pins sqlalchemy>=2.0,<3
pip install <your DBAPI driver>    # user-supplied: pymysql, pyodbc, ...
export QUALIS_ADAPTER=sqlalchemy
export QUALIS_DATABASE_URL='mysql+pymysql://user:pass@host/db'
```

All checks are SQLAlchemy **Core expressions** — no raw SQL strings — so one
implementation targets every dialect SQLAlchemy 2.x speaks, injection-safe
by construction. Dialect notes:

- **regex checks** use `regexp_match`; on SQLite the adapter installs a
  Python `regexp()` function at connect time (SQLite documents REGEXP as
  user-supplied). Dialects whose servers lack a regex operator will error
  clearly rather than silently pass.
- **duplicate_count** = non-null values − distinct non-null values
  ("extra copies").

## Reference JOIN mode

`reference_lookup` rules whose reference data is a **table in the checked
database** can set `reference_schema` in their parameters: qualis probes
`table_exists(reference_schema, reference)` and, when confirmed, validates
membership with a NULL-safe `NOT EXISTS` correlated subquery — zero Python
materialization of the value set. Probe failure or a missing
`check_reference_join` capability skips loudly (detected, never assumed —
AgDR-0006). The `NOT EXISTS` form is a capability contract: `NOT IN
(subquery)` silently zeroes counts when the reference key contains NULLs.
Adapters without `check_reference_lookup` at all now skip with a reason
(the old full-column Python fallback is removed).

| Adapter | JOIN mode |
| --- | --- |
| duckdb / postgres / sqlalchemy | **Supported** |
| in_memory | N/A — its reference data IS the port; values path |
| qualis-snowflake / qualis-bigquery | Not yet (values path works as before) |

## Timeout-honesty matrix

`QUALIS_STATEMENT_TIMEOUT_MS` protects runs from one slow table — but only
where the engine actually supports a per-statement timeout. qualis never
fakes it:

| Adapter | Statement timeout | Mechanism |
| --- | --- | --- |
| postgres | **Real** | `SET LOCAL statement_timeout` per check transaction |
| duckdb | **Absent** | DuckDB has no per-statement timeout; use OS-level limits |
| in_memory | Not applicable | In-process Python |
| sqlalchemy | **Absent (v1)** | Dialect-specific; not implemented rather than faked. Use a native adapter or server-side limits |
| qualis-snowflake | See its README | `STATEMENT_TIMEOUT_IN_SECONDS` is engine-side |
| qualis-bigquery | See its README | Job-level `timeoutMs` is engine-side |

If a check hangs on an adapter marked **Absent**, that is expected behavior
documented here — not a bug in the timeout setting.

## Condition-support matrix

`Rule.condition` filters the checked population (AgDR-0005). Conditions are
parsed against a constrained grammar at rule **load** time — the parser is
the trust boundary, whatever the condition's source (rule YAML, dbt `meta`).
A conditioned rule on an adapter without support is **skipped with a visible
reason**, never run unfiltered.

| Adapter | Conditions | Mechanism |
| --- | --- | --- |
| in_memory | **Supported** | AST evaluated in Python per row |
| duckdb | **Supported** | AST → SQL fragment, values inlined with quote-doubling (grammar-bounded) |
| postgres | **Supported** | AST → SQL fragment, values as psycopg named binds |
| sqlalchemy | **Supported** | AST → Core `ColumnElement[bool]`, `&`-composed into counts AND samples |
| qualis-snowflake / qualis-bigquery | Not yet | Conditioned rules skip with a reason until the siblings implement the kwarg |

Grammar v1: comparisons (`= != <> < <= > >=`), `IS [NOT] NULL`,
`[NOT] IN (...)`, `AND`/`OR`, parentheses, single-quoted strings (with `''`
escapes), signed numbers. No functions, casts, subqueries, or cross-column
comparisons — by design. A condition matching **zero rows** yields a skipped
check ("condition matched no rows") so vacuous checks cannot inflate scores.
