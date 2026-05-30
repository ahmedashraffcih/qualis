# Qualis GitHub Action

Run Qualis checks on every PR and get a quality scorecard posted as a comment.

## Usage

```yaml
name: Data Quality
on:
  pull_request:
    paths:
      - 'data/**'
      - 'rules/**'

jobs:
  qualis:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: ahmedashraffcih/qualis@v0.2.0
        with:
          rules: rules/
          sample: data/accidents.csv
          fail-on-score: "80"
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `rules` | Path to the directory containing YAML rule files | no | `rules` |
| `sample` | CSV or Parquet sample file to validate | yes | — |
| `fail-on-score` | Exit non-zero when aggregate score falls below this (0–100) | no | `0` |
| `python-version` | Python version to install | no | `3.12` |
| `qualis-version` | Pinned Qualis version on PyPI | no | latest |

## What gets posted

A sticky PR comment (replaced on each push) with:

- Overall score badge
- Per-DAMA-dimension pass/warn/fail
- Total + critical violation count
- Commit SHA

The full JSON report is also uploaded as an artifact for later inspection.

## Permissions

The job needs `pull-requests: write` to post the comment. The `actions/upload-artifact` step needs `contents: read`.

## Local equivalent

The action shells out to `qualis report --format json` then renders the comment via `python -m qualis.github`. To preview what would be posted, run:

```bash
qualis report --rules rules/ --sample data/accidents.csv --format json --output qualis-report.json
python -m qualis.github qualis-report.json
```
