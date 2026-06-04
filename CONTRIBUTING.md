# Contributing to Qualis

Thanks for considering a contribution! A few notes that will save us both time.

## Setup

```bash
git clone https://github.com/ahmedashraffcih/qualis
cd qualis
uv sync --all-extras --dev
uv run pre-commit install   # one-time: wires the commit-time checks below
uv run pytest -q
```

Expected: 471+ tests pass.

Pre-commit runs `ruff check`, `mypy src/` (via `uv run`, so versions match
CI exactly), plus YAML / whitespace sanity on every commit — the same gates
CI enforces, with a seconds-long feedback loop instead of a CI round-trip.
Run on demand with `uv run pre-commit run --all-files`. Tests are
deliberately not in pre-commit (too slow per-commit); run them before
pushing.

## Quality bar

- Tests pass: `uv run pytest`
- Type checks pass: `uv run mypy src/` (strict mode; zero errors)
- Lint passes: `uv run ruff check src/ tests/` (zero warnings)
- Coverage stays above 80%: `uv run pytest --cov=qualis --cov-fail-under=80`

CI enforces all four. PRs that don't meet the bar will be redirected.

## Branch naming

`feature/<short-description>` for new functionality
`fix/<short-description>` for bug fixes
`docs/<short-description>` for docs-only changes
`chore/<short-description>` for tooling / release / CI

## Commits

Conventional Commits style:

- `feat: ...` for new functionality
- `fix: ...` for bug fixes
- `chore: ...` for tooling / release work
- `docs: ...` for documentation
- `refactor: ...` for internal restructuring without behaviour change
- `test: ...` for test-only changes

Keep the first line under 72 chars. Use the body to explain the why.

## Domain rules

Qualis is hexagonal. The `src/qualis/domain/` layer has zero external
imports (only stdlib + `qualis.domain.*`). Ports are `typing.Protocol`
interfaces. Adapters implement ports and live under `src/qualis/adapters/`.
Don't violate the dependency direction — if you need it, file an issue
to discuss the design first.

## Releasing

See `docs/release.md`.
