# Notifier implementations: stdlib HTTP, env-only secrets, isolated dispatch

> In the context of implementing the first `NotifierPort` adapters (Slack + generic webhook, qualis#20), facing the choice of HTTP client, secret-configuration mechanism, and failure semantics, I decided to use stdlib `urllib.request` with `SecretStr` env-var settings and a centralized isolating dispatcher, to achieve zero new dependencies and a notifier that can never fail a check run or leak a secret into YAML, accepting a less ergonomic HTTP API than httpx/requests.

## Context

`NotifierPort` has been a bare Protocol since v0.3 — exported in the public API, implemented by nobody, called by nobody. The v0.6.0 design review (candidate E, AMBER) set two blocking constraints: (1) a notifier failure must NEVER fail or abort the check run; (2) webhook URLs/tokens must never appear literally in YAML. Plus a hard HTTP timeout, single-attempt v1, and summarized payloads (Slack 40KB cap).

## Options Considered

| Option | Pros | Cons |
| --- | --- | --- |
| **stdlib `urllib.request` (chosen)** | Zero new dependency for a feature many users won't enable; one POST per run needs no pooling | Clunkier API; manual header/timeout handling |
| `httpx` optional extra | Modern API, async-ready | A dependency + extra for one POST; async unneeded (CLI exits after run) |
| `requests` | Ubiquitous | Sync-only legacy dependency; same overkill |
| **Secrets via `QUALIS_*` env settings, `SecretStr` (chosen)** | No YAML surface exists at all — stronger than `{{ env.* }}` indirection (nothing to template); pydantic masks reprs | Notifier URLs not per-rules-file configurable in v1 |
| `notifiers:` block in rules YAML with `{{ env.* }}` URLs | Per-dataset routing | Creates a YAML surface that *can* hold a literal secret; defers the leak to user discipline |
| **Isolation in a `dispatch_notifications` helper (chosen)** | One enforcement point; notifiers stay simple and testable; mirrors `rule_engine` sampling-fallback shape | Direct `notify_results` calls bypass isolation (documented: dispatch is the supported entry) |
| try/except inside each notifier | No bypassable path | Duplicated isolation logic; failures invisible to tests that want them |

## Decision

- `src/qualis/adapters/notifiers/` package: `SlackWebhookNotifier` (Slack `{"text": ...}` payload) and `WebhookNotifier` (generic JSON), both `urllib.request` POSTs with a 10s default timeout, single attempt, no retry.
- Constructors validate the URL scheme is `http`/`https` (rejects `file://` et al. at build time — `urlopen` would otherwise follow any scheme).
- `QualisSettings.slack_webhook_url` / `webhook_url` as `SecretStr` env fields (`QUALIS_SLACK_WEBHOOK_URL`, `QUALIS_WEBHOOK_URL`). The composition root `bootstrap.build_notifiers(settings)` constructs whichever are configured.
- `dispatch_notifications(notifiers, score)` wraps EACH notifier in try/except, logs a warning on failure, never raises. CLI gate: `qualis check --notify` (explicit enable), skipped under `dry_run`.
- Payloads are summaries: dataset, score pct, violation counts, up to 10 worst dimensions. Never violation samples.

## Consequences

- `qualis[all]` stays dependency-free for notifications; Slack alerting works out of the box
- A hanging endpoint costs at most `timeout` seconds per configured notifier, then the run completes normally
- Non-2xx responses surface as logged warnings via `HTTPError` through the dispatcher — "single attempt + log" with no extra code
- v2 candidates (explicitly deferred): retry/backoff, per-rules-file notifier routing, severity-threshold filtering, richer Slack blocks

## Artifacts

- Ticket: ahmedashraffcih/qualis#20 · Design review: ops repo `projects/qualis/design-reviews/2026-06-06-tariq-v060-perf-edge-case-pass.md` (candidate E)
