# Bound CheckResult.violations to a capped sample

> In the context of count-only checks at production scale, facing O(failing-rows) memory from `[Violation(...)] * count` at 7 sites in `rule_engine.py`, I decided to make `violations` a bounded sample (≤ `MAX_SAMPLE_VIOLATIONS`, one representative placeholder today) with `violation_count` authoritative, to achieve constant memory per check, accepting that row-level detail waits for the `--sample-rows` feature.

## Context

`CheckResult` carries both `violation_count: int` and `violations: list[Violation]`. Adapters return count dicts only — no row data reaches the engine — so every multiplied `Violation` is an identical placeholder (`record_id=None`, `actual_value=None`). All report/console/scoring consumers read `violation_count`; only the redaction pass in `engine/checker.py` iterates the list. A 10M-row failure allocates a 10M-slot list for zero information gain. Identified as v0.5.0 hardening item 1 (internal dogfood review; spec reconstructed in the ops repo).

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Empty list + count only | Smallest objects | Neuters the redaction path and its regression test; `count=N, violations=[]` reads like a bug; no debugger affordance |
| **One representative placeholder, capped list contract** | O(1) memory now; keeps redaction meaningful; list slot becomes the natural container for real `--sample-rows` samples later; breaks zero existing tests | Placeholder still carries no row data (acceptable — none exists yet) |
| New `violations_sampled: bool` field | Explicit truncation signal | Derivable from `violation_count > len(violations)`; redundant state on a frozen dataclass; no current consumer needs it |

## Decision

Chosen: **one representative placeholder + capped-list contract**, because it removes the O(n) allocation with the smallest behavioural surface, keeps every existing test green, and is forward-compatible with `--sample-rows` filling the same bounded container with real rows. `MAX_SAMPLE_VIOLATIONS: Final[int] = 100` lives in `domain/models.py` next to the contract it bounds. The redaction `object.__setattr__` hack in `checker.py` is replaced with `dataclasses.replace` in the same change — its only justification (mutating millions of instances cheaply) disappears once the list is bounded.

## Consequences

- `violation_count` is the only valid source of failure counts; deriving counts from `len(violations)` is documented as wrong
- `--sample-rows` (v0.5.0 PR 2) populates the same list with real `Violation`s, sliced to the cap inside `_sample`
- Domain stays genuinely immutable — no more frozen-dataclass back-door writes
- No public API or `DatabasePort` change; sibling adapters unaffected

## Artifacts

- Ticket: ahmedashraffcih/qualis#2
- Spec: ops repo `projects/qualis/specs/2026-06-04-v050-hardening-plan.md` (item 1)
