# Condition pushdown: constrained grammar, count semantics, per-adapter rendering

> In the context of making `Rule.condition` actually filter the checked population, facing the rejected raw-SQL-WHERE design (injection surface on string-templated adapters, no count-semantics decision, sampling evidence divergence — Solution Architect review 2026-06-05, blockers B1–B3/XC-B1/XC-B2), I decided to define a small constrained condition grammar parsed to a domain AST and rendered per adapter, to achieve safe-by-source-agnostic filtering with consistent semantics, accepting that v1 expressiveness is deliberately limited (no functions, casts, subqueries, or cross-column comparisons).

## Context

`Rule.condition: str | None` exists on the model and loads from YAML, but execution ignores it and the discovery writer drops it — a silent correctness trap. Conditions are untrusted text by policy: today they come from rule YAML, v0.5.1 pipes them from dbt `schema.yml meta` across a repo boundary, and discovery/LLM suggestion may author them later. Two adapters (duckdb, postgres) build SQL by string templating; one (duckdb) has no bind path at all. PR 4 landed a SQLAlchemy Core layer that composes predicates safely.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Raw SQL WHERE passthrough (original spec) | Maximum expressiveness, no parser | Injection-shaped surface on string-templated adapters; unparseable → unportable across dialects; cannot be threaded into sampling predicates safely. REJECTED by design review |
| Transpile full SQL via a parser dependency (e.g. sqlglot) | High expressiveness, real dialect transpilation | New heavyweight dependency for a governance-critical path; the full SQL surface IS the threat surface — parsing it all means allowing most of it |
| **Constrained grammar → domain AST → per-adapter renderers (chosen)** | The boundary is an allowlist: only enumerated constructs exist past the parser; identical semantics provable across adapters; AST `&`-composes into Core and threads into sampling for free | v1 expressiveness limited; a hand-rolled parser to maintain (small: ~9 constructs) |

## Decision

**Grammar v1** (everything else is a load-time `ValueError`):

```text
condition  := or_expr
or_expr    := and_expr (OR and_expr)*
and_expr   := unary (AND unary)*
unary      := '(' or_expr ')' | predicate
predicate  := column op literal
            | column IS [NOT] NULL
            | column [NOT] IN '(' literal (',' literal)* ')'
op         := = | != | <> | < | <= | > | >=
column     := bare identifier (letters, digits, underscore; same-table only)
literal    := single-quoted string | integer | decimal number
```

- **Trust boundary = the parser** (`domain/condition.py`). Validation happens at rule LOAD time (`config/loader.py`), not execution — a bad condition never reaches an adapter, whatever its source.
- **Count semantics**: with a condition, `rows_checked` = the condition-matching population; `violation_count` = failures within it; `total_count` reported by adapters stays population-scoped. A condition matching **zero rows** yields `skipped=True` ("condition matched no rows") — vacuous checks must not inflate the aggregate score (same principle as the v0.4.1 sql/custom SKIPPED fix).
- **Per-adapter rendering** from the AST: in_memory evaluates the AST in Python; sqlalchemy renders a Core `ColumnElement[bool]` and `&`-composes it with check predicates — which **automatically applies it to `fetch_violation_samples`**, closing review blocker B3; postgres renders parameterized SQL (`%(c_N)s` binds); duckdb renders escaped literals — safe because the renderer's output space is the grammar's, not the user's.
- **Honesty rule**: a conditioned rule on an adapter without condition support returns `skipped` with a reason — never a silently unfiltered count.
- **Round-trip**: `discover/writer.py` serializes `condition` back to YAML.

Pre-Build review additions (Solution Architect sign-off 2026-06-05, conditions C1–C5):

- **Signed numeric literals** are part of the grammar (`balance > -100`): the lexer accepts a leading `-` on numbers. **`IN ()` with zero elements is a load-time error** (always-false predicates are author mistakes, not filters); single-element `IN` is fine.
- **Load-time errors are located**: file + rule id + the offending substring (the `_check_for_duplicate_ids` loud-failure ethos).
- The parser validates **shape, not column existence** — a condition naming a missing column surfaces as a located check error at execution, never an opaque adapter traceback.
- Bare identifiers render through each adapter's **double-quoted identifier** path, so reserved-word columns (`order`, `select`) work.
- The docs gain a **per-adapter condition-support matrix** beside the timeout matrix — a skipped condition is acceptable only if visible.

## Consequences

- dbt-sourced conditions (v0.5.1) inherit the allowlist boundary unchanged — XC-B2 closed by construction
- Grammar extensions (BETWEEN, booleans, NULL-safe equality) are additive parser changes with per-adapter renderer updates; each extension is a reviewable decision
- The UNIQUE check's group/HAVING shape applies the condition in the inner population scan on every adapter (review trap B2 noted in implementation)
- Sibling adapters without condition rendering degrade to `skipped` on conditioned rules until they implement it

## Artifacts

- Ticket: ahmedashraffcih/qualis#12
- Design review driving this: ops repo `projects/qualis/design-reviews/2026-06-05-tariq-v050-pr3-pr4-review.md`
- Foundation: AgDR-0004 (Core-expression layer)
