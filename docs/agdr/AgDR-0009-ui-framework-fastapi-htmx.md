# qualis UI framework: FastAPI + Jinja2/HTMX behind a `qualis[ui]` extra

> In the context of building a local browser UI so non-developer testers can run the full data-quality journey from a CSV (qualis#27, PRD 2026-06-07), facing the choice of UI framework, packaging, and bind/port strategy, I decided to use FastAPI + server-rendered Jinja2 + HTMX (no build step) behind an optional `qualis[ui]` dependency group, to achieve a strict-mypy-clean driving adapter that reuses the existing application services with minimal install friction, accepting a less batteries-included developer experience than an all-in-one framework like Streamlit/NiceGUI.

## Context

qualis is a pip-installed CLI library. The UI is an opt-in convenience for testers, not a long-lived web service, so dependency weight and install friction dominate the decision. The project enforces `mypy --strict` as a hard gate, and CSV cell content is untrusted input the moment a browser renders it — so the framework's typing story and its localhost-bind defaults are first-class criteria. Full feasibility analysis: ops repo `projects/qualis/design-reviews/2026-06-07-tariq-ui-feasibility.md`.

## Options Considered

| Option | Pros | Cons |
| --- | --- | --- |
| **FastAPI + Jinja2/HTMX, no build step (chosen)** | Types cleanly under `mypy --strict` (Pydantic-native, matches the stack); explicit `127.0.0.1` bind; Jinja2 already a base dep with `select_autoescape`; HTMX gives live partial swaps with zero node toolchain | Less batteries-included than an all-in-one; we hand-author routes + templates |
| Streamlit | Fast to prototype | Pulls pandas/pyarrow/altair (heaviest); script-rerun model fights a stateful 6-screen wizard; poor strict-typing story; binds 0.0.0.0 by default |
| NiceGUI | Closest all-in-one app fit; explicit state model | Ships a compiled Vue/Quasar bundle (opaque dep weight); leaks `Any` at the UI boundary under strict mypy; 0.0.0.0 default |
| Gradio | Quick I/O demos | Heavy deps; designed for I/O blocks not multi-screen wizards; shared-link feature is a localhost-safety risk; 0.0.0.0 default |
| Flask + vanilla | Lightest footprint | Re-implement typed request handling by hand; no async for progress streaming |

## Decision

- **FastAPI** as the HTTP layer (OQ-1) — Pydantic-native, strict-mypy clean, async future-proofs long-check progress.
- **Server-rendered Jinja2 + HTMX, no build step** (OQ-2) — HTMX gives partial-DOM swaps (live status badges) without a node toolchain; Alpine.js may be vendored for small client niceties. Jinja2 `select_autoescape` (already used in `report/scorecard.py`) is the XSS defense for untrusted CSV content.
- **`pip install 'qualis[ui]'` optional-dependency group** (OQ-6) — FastAPI/uvicorn stay out of the base install that CI-only users pay for. `qualis ui` lazy-imports its deps inside the handler and prints a clean install hint when the extra is absent.
- **Port strategy** (OQ-7) — default 7420; if bound, scan 7421→7430 and print the actual URL; `--port` overrides and disables the scan.
- **Bind `127.0.0.1` only** — hard-coded, no flag widens it in v1 (untrusted-CSV LAN-exposure guard).
- **Driving-adapter architecture** — `src/qualis/ui/` holds zero domain logic; every action delegates to the existing services (`profile_table`, `suggest_rules`, the review `state_machine`, `create_checker`, `suggestions_to_yaml`, `save_html_report`).
- **NEEDS_EVIDENCE serialization** — exported via the existing `metadata.needs_evidence_reason` key (machine-readable, round-trips through the loader), not a YAML comment which `yaml.safe_dump` cannot emit.

## Consequences

- The UI ships as a thin presentation layer over services that already exist and are tested — v1 is mostly wiring + templates.
- Base-install users are unaffected; only `qualis[ui]` adopters pull FastAPI/uvicorn.
- Three security edges become acceptance criteria on the build tickets: XSS via CSV cell content (autoescape), 127.0.0.1-only bind, and tempfile-sandboxed uploads (which also defuses the pre-existing raw-path quoting in `register_csv`).
- Hand-authored routes/templates are more code than an all-in-one, accepted for the typing + footprint + security wins.

## Artifacts

- Ticket: ahmedashraffcih/qualis#27 (PR-1) · PRD: ops `projects/qualis/prds/2026-06-07-qualis-ui-v1.md` · Feasibility: ops `projects/qualis/design-reviews/2026-06-07-tariq-ui-feasibility.md`
