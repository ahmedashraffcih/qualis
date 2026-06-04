# Trunk-based branch model with protected main

> In the context of qualis gaining real users (PyPI) and real contributors (portfolio governance), facing direct pushes to main with red CI (v0.4.0/v0.4.1 shipped that way), I decided to stay trunk-based with server-side branch protection to achieve enforced review + green-CI merges, accepting that release isolation comes from tag-driven publishing rather than a development branch.

## Context

Until 2026-06-04 nothing prevented direct pushes to `main`: v0.4.0 and v0.4.1 landed without PRs, the latter while CI was red (a coverage-gate misconfiguration fixed in #3). The portfolio's governance framework (ApexYard) requires every change through a PR with review and green CI, and explicitly reserves the dev/main release-cut model for the framework repo itself — managed projects stay trunk-based. Qualis does have downstream consumers (PyPI: qualis, qualis-snowflake, qualis-bigquery), which is the usual argument for a dev branch.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Trunk-based + protected main + tag-driven releases** | One merge per change; nothing reaches PyPI until a tag is pushed (release isolation without a second branch); matches ApexYard's managed-project rule | History on main includes unreleased work (acceptable — versioning is tag-anchored) |
| dev/main split (framework-style) | main always equals latest release | Double-merge ceremony per change; release PR overhead; ApexYard explicitly warns against cargo-culting it into managed projects |
| Unprotected main (status quo) | Zero friction | Demonstrated failure mode: unreviewed red-CI pushes shipping to the default branch |

## Decision

Chosen: **trunk-based + protected main**, because tag-driven PyPI publishing already provides the consumer-facing isolation a dev branch would buy, at zero extra merge ceremony. Protection applied 2026-06-04:

- Require a pull request before merging (`required_approving_review_count: 0` — solo-maintainer repo; GitHub forbids self-approval, so a 1-review requirement would deadlock every merge; review enforcement lives in the governance layer's reviewer + approval marker gates)
- Required status checks, strict mode: `test (Python 3.12)`, `test (Python 3.13)`
- `enforce_admins: true` — the owner's pushes are not exempt
- Force pushes and branch deletion blocked

## Consequences

- Every change — including docs and this file — goes through a PR with green CI
- Renaming the CI matrix jobs silently empties the required-checks gate; update the protection contexts whenever `ci.yml`'s job names change
- Hotfixes follow the same path (branch → PR → green CI → merge → tag); no hotfix branch class
- If a second regular maintainer joins, revisit `required_approving_review_count`

## Artifacts

- Ticket: ahmedashraffcih/qualis#4 (protection config applied and verified in the ticket thread)
- Related: ahmedashraffcih/qualis#3 (CI gate repair that made required checks meaningful)
