# Qualis

> **Data quality rules you can sign off on.**

The generation is the commodity. The grounding, the control, and the
upkeep are the value. Qualis is the open-source Python framework that
treats your DQ rulebook as a versioned artefact — grounded in declared
context (sentinels, exceptions, business grain), reviewed under a real
approval workflow, and validated against your programme's required
metadata standard.

*Qualis* — Latin for "of what kind."

Define rules in plain YAML, run them against CSV/Parquet files or any
database via a pluggable adapter, and get a scored report that names
the failing rows, columns, and rules — so your team can act immediately.

---

## Quick start

```bash
pip install qualis

# Scaffold a new project
qualis init

# Edit rules/completeness.yaml, then run against a sample
qualis check --rules rules/ --sample data.csv
```

---

## Example rule

```yaml
rules:
  - id: DQ-COMP-001
    name: "Accident date is required"
    dimension: completeness
    severity: critical
    dataset: accidents
    column: accident_date
    check: not_null
```

Rules can carry a **`condition`** that scopes the checked population —
parsed against a small safe grammar at load time, never raw SQL:

```yaml
  - id: DQ-COMP-002
    name: "Closed accidents must carry a report date"
    dimension: completeness
    severity: warning
    dataset: accidents
    column: report_date
    check: not_null
    condition: "status = 'closed' AND severity_code != 'PROPERTY'"
```

Cross-dataset assertions compare an aggregate between two tables in the
same database — the check that catches a transformation (increasingly
AI-written) that silently dropped rows:

```yaml
  - id: DQ-CONS-001
    name: "Fact row count tracks staging within 2%"
    dimension: consistency
    severity: critical
    dataset: marts.orders
    check: cross_dataset_assertion
    parameters:
      metric: row_count            # v1: row_count | sum
      reference_dataset: staging.orders
      tolerance_pct: "2"
```

Supported checks: `not_null`, `unique`, `between`, `regex`, `in_set`,
`row_count`, `not_negative`, `reference_lookup` (values or same-database
JOIN mode), `cross_dataset_assertion`, plus `sql` / `custom` stubs.

---

## CLI reference

```
qualis init [DIRECTORY]          Scaffold rules/ and .gitignore
qualis validate --rules PATH     Validate YAML syntax, list rules
qualis check                     Run checks and print a score report
  --rules   PATH                 Rules directory (required)
  --sample  PATH                 CSV or Parquet file to check; omit to run
                                 against the configured adapter (below)
  --sample-rows N                Attach up to N real failing rows per
                                 violated rule as evidence (max 100)
  --fail-on-score N              Exit 1 when score < N (0-100)
  --allow-custom                 Allow custom check type
  --output-format table|json     Output format (default: table)
  --notify                       Send a score summary to configured
                                 notifiers (see Notifications)
qualis version                   Print version
```

---

## Notifications

`qualis check --notify` pushes a bounded score summary (score, violation
counts, worst dimensions — never row-level data) to Slack and/or a generic
JSON webhook:

```bash
export QUALIS_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export QUALIS_WEBHOOK_URL="https://alerts.example.com/qualis"   # optional second sink
qualis check --rules rules/ --sample data.csv --notify
```

Endpoints are configured **only** through environment variables — webhook
URLs embed tokens, and there is deliberately no YAML field for them, so a
secret can never end up committed in a rules file. A notifier failure
(timeout, DNS, 500) is logged as a warning and never fails the check run;
notifications are skipped entirely under `QUALIS_DRY_RUN`. Single attempt,
10s hard timeout, no retries.

---

## Databases

Skip `--sample` and qualis runs against a configured database adapter:

```bash
# Postgres (native adapter, real per-statement timeouts)
export QUALIS_ADAPTER=postgres
export QUALIS_DATABASE_URL='postgresql://user:pass@host/db'
export QUALIS_STATEMENT_TIMEOUT_MS=30000   # one slow table can't hang a run

# ...or ANY engine SQLAlchemy 2.x speaks (MySQL, MSSQL, Oracle, Trino, SQLite)
pip install 'qualis[sqlalchemy]' your-dbapi-driver
export QUALIS_ADAPTER=sqlalchemy
export QUALIS_DATABASE_URL='mysql+pymysql://user:pass@host/db'

qualis check --rules rules/ --sample-rows 5
```

Built-ins: `duckdb` (default, also powers `--sample`), `in_memory`,
`postgres`, plus the `sqlalchemy` meta-adapter. Third-party adapters
(e.g. [`qualis-snowflake`](https://pypi.org/project/qualis-snowflake/),
[`qualis-bigquery`](https://pypi.org/project/qualis-bigquery/)) plug in
via the `qualis.adapters` entry-point group. Per-adapter feature honesty
(timeouts, conditions) is documented in [`docs/adapters.md`](docs/adapters.md).

Reference lookups validate in-database when the reference is a co-located
table — set `reference_schema` in the rule's parameters and qualis JOINs
instead of materializing the value set (detected via a `table_exists`
probe, never assumed).

---

## How it compares

| Feature | Qualis | Great Expectations | Soda Core | dbt tests |
|---------|--------|--------------------|-----------|-----------|
| Declarative YAML rules | Yes | Partial | Yes | Yes |
| Tells you WHAT failed | Yes | Partial | Partial | No |
| Zero-config CSV check | Yes | No | No | No |
| Weighted scoring | Yes | No | No | No |
| Pluggable adapters | Yes | Yes | Yes | No |
| Python API | Yes | Yes | Yes | Yes |
| Standalone CLI | Yes | No | Partial | No |

---

## Python API

```python
from qualis import DQDimension, DatasetScore, Rule
from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.config.loader import load_rules_from_directory
from qualis.engine.checker import CheckRunner
from pathlib import Path

adapter = DuckDBAdapter()
adapter.register_csv("accidents", Path("data/accidents.csv"))

rules = load_rules_from_directory(Path("rules/"))
weights = {
    DQDimension.COMPLETENESS: 0.40,
    DQDimension.VALIDITY: 0.35,
    DQDimension.UNIQUENESS: 0.25,
}
runner = CheckRunner(adapter=adapter, rules=rules, weights=weights)
score: DatasetScore = runner.run()

print(f"Score: {score.aggregate_score:.0%}")
print(f"Violations: {score.total_violations} ({score.critical_violations} critical)")
```

---

## Example

See [`examples/traffic_safety/`](examples/traffic_safety/) for a complete
worked example with a synthetic road-accident dataset.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
