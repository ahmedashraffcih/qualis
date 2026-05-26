# Traffic Safety Example

This example demonstrates Qualis against a synthetic road-accident dataset.
It covers all three primary data quality dimensions: completeness, validity,
and uniqueness.

## Dataset

`data/accidents.csv` contains 11 rows with deliberate quality issues:

| Row | Issue |
|-----|-------|
| 3 | Missing `accident_date` (completeness violation) |
| 4 | Missing `location_id` (completeness violation) |
| 6 | `severity_code = INVALID` — not in the allowed set (validity violation) |
| 11 | Duplicate `id = 1` (uniqueness violation) |

## Rules

| File | Checks |
|------|--------|
| `rules/completeness.yaml` | `accident_date`, `severity_code`, `location_id` must be non-null |
| `rules/validity.yaml` | `accident_date` within range, `severity_code` matches known values |
| `rules/uniqueness.yaml` | `id` must be unique |

## Running

From the repository root:

```bash
# Table output (default)
qualis check \
  --rules examples/traffic_safety/rules/ \
  --sample examples/traffic_safety/data/accidents.csv

# JSON output
qualis check \
  --rules examples/traffic_safety/rules/ \
  --sample examples/traffic_safety/data/accidents.csv \
  --output-format json

# Fail if score drops below 80
qualis check \
  --rules examples/traffic_safety/rules/ \
  --sample examples/traffic_safety/data/accidents.csv \
  --fail-on-score 80
```

Expected aggregate score: approximately 70-80 (four violations across six rules).
