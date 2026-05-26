# Qualis

**Data quality framework that tells you what failed, not just that something did.**

> *Qualis* — Latin for "of what kind."

Qualis lets you define data quality rules in plain YAML and run them against
CSV or Parquet files (or any database via a pluggable adapter).  The output is
a scored report that names the failing rows, columns, and rules — so your team
can act immediately instead of hunting through raw data.

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

Supported checks: `not_null`, `unique`, `between`, `regex`, `sql`.

---

## CLI reference

```
qualis init [DIRECTORY]          Scaffold rules/ and .gitignore
qualis validate --rules PATH     Validate YAML syntax, list rules
qualis check                     Run checks and print a score report
  --rules   PATH                 Rules directory (required)
  --sample  PATH                 CSV or Parquet file to check (required)
  --fail-on-score N              Exit 1 when score < N (0-100)
  --allow-custom                 Allow custom check type
  --output-format table|json     Output format (default: table)
qualis version                   Print version
```

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
