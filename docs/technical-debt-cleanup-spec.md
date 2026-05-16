# T-Sense Technical Debt Cleanup Spec

Date: 2026-05-13
Status: Active debt register and documentation ownership index

This file is the current authority for technical-debt status. The detailed
2026-05-13 implementation log in
`docs/quality/2026-05-13-tech-debt-iteration-log.md` is historical evidence,
not the current task state. The live handoff summary lives in
`docs/quality/task-state.md`, and local command recipes live in
`docs/testing.md`.

## Goal

Make T-Sense easier to change without weakening the product guarantees that now
matter most: local-first privacy, stable agent JSON contracts, safe dashboard
actions, repeatable monitor runs, and a usable Signal Desk surface.

This cleanup is not a cosmetic refactor. The intended outcome is that future
feature work can land in smaller files, with clearer ownership, faster review,
and contract tests that prevent silent product regressions.

## Current Baseline

Observed from the 2026-05-15 local workspace:

- Current branch: `master`; the worktree was clean before this doc/graph cleanup
  slice and local `HEAD` was one commit ahead of `origin/master`.
- The dirty checkpoint backlog from the documentation handoff has been split,
  verified, and committed through packaging, report, scan, monitor, Bot Gateway,
  dashboard server tests, and dashboard settings UI slices.
- Future cleanup should start from a fresh focused slice instead of treating the
  old dirty handoff as still active.
- Each implementation checkpoint used focused mixed-tree verification first and
  staged snapshot verification before commit. Docker packaging smoke was later
  verified locally after Docker Desktop became reachable.
- CI still covers Python 3.12/3.13 on Linux, Windows, macOS; ruff; pytest;
  dashboard tests/build; shell syntax; POSIX launcher LF line endings.

## Product Guardrails From 2026-05-14 Research Refresh

`ROADMAP.md` owns the market snapshot and source list. The technical debt
consequence is narrower: future cleanup must not regress the v0.5 activation
and decision-loop behaviors that distinguish T-Sense from generic Telegram
summaries, digest bots, and RSS/intelligence-feed tools.

Guardrails for future splits and refactors:

- Preserve the first-use next-action path. `Start` should surface one current
  executable step before optional or already-complete setup work, because the
  local-first setup path is harder than a hosted bot or saved feed.
- Preserve private Bot Gateway ordering. Background/bot automation controls
  must remain blocked until token and authorized chat are both ready; do not
  broaden bot behavior before the narrow dry-run/status/dashboard handoff is
  reliable.
- Preserve Settings notification repair. A zero-target state must still let the
  user create or repair the default private Telegram notification target from
  the dashboard instead of falling back to hidden CLI setup.
- Preserve review follow-through. When the latest-action queue is empty but
  open historical review work exists, Inbox should prefer the highest-value
  open backlog bucket before handled items.
- Treat "first useful decision" as the product benchmark for quality slices:
  time to first explainable keep/skip/follow-up action, plus evidence that
  feedback changes a later scan, matters more than the polish of the generated
  digest.

## Recently Resolved Product Debt From Issue #7

GitHub issue #7 was closed on 2026-05-15 after commit `c94de3e` resolved the
personal developer-opportunity monitor friction slice. Its 2026-05-14 comments
remain useful evidence, but they are no longer the current open debt register.

Resolved behaviors to preserve:

- The default jobs workflow is frontend-focused and treats backend-only,
  generic full-stack, CV/resume, and self-promotion posts as non-vacancy or
  low-signal boundary cases.
- Manual/full report output is explicitly documented as report-only unless it
  goes through the monitor card-ingestion path.
- Dashboard-openable report artifact paths and canonical source evidence are
  covered by existing review-card/report-path behavior and tests.
- Settings > Alerts exposes a Bot Gateway repair action that can restart or
  kick an installed stale background gateway.

Future work should open a new issue or a new spec section only for a verified
regression or a new product slice; do not keep treating all of #7 as open work.

## Progress Update: 2026-05-13 Hardening Iteration

The 2026-05-13 hardening branch established a clean-HEAD baseline independent
of unrelated dirty WIP:

- Detached clean worktree gate passes: `python -m ruff check .`,
  `python -m pytest -q` (`435` passed, `2` skipped, `180` subtests),
  `cd dashboard; npm test -- --run` (`18` files, `131` tests), and
  `cd dashboard; npm run build`.
- Canonical local gate commands now live in `docs/testing.md`; full dirty
  worktree verification must use a detached `git worktree`, while
  checkout-index snapshots are for targeted staged checks only.
- Shared contract fixtures now cover agent envelopes, semantic items, monitor
  run results, run manifests, dashboard state, Desk actions/sources/results,
  source-access summaries, settings token/AI-key status, and settings client
  status/mutation responses.
- `agent_extraction_request_v1` no longer serializes local input/profile/output
  handoff paths into the copyable request document; those writable paths remain
  in the local JSON envelope.
- Bot Gateway status fixture coverage was later isolated as a checkpoint. Live
  Telegram API, live scheduler, keyring, and structured LLM behavior were
  verified as workstation operator checks on 2026-05-14.

The next cleanup phase should build on this baseline rather than re-litigating
whether contract/privacy fixtures are worth keeping. New splits should either
reuse these fixtures or add similarly shared fixtures before moving behavior.

## Progress Update: 2026-05-14 Checkpoint Run

The documentation-debt pass converted the old dirty-tree handoff into current
authority docs, then the implementation work was committed one checkpoint at a
time:

- Packaging metadata and the `tgcs` facade now have package metadata tests,
  local build/install smokes, `pipx`, and `uvx` coverage. Docker smoke is still
  an operator/environment check until a daemon is available.
- `report.py`, `scan.py`, `monitor.py`, `monitor_state.py`, and
  `bot_gateway.py` now act as smaller facades or focused boundaries backed by
  new modules and focused test directories.
- `tests/test_dashboard_server.py` was split into `tests/dashboard/`, and
  dashboard Markdown/HTML artifact rendering moved to `scripts/dashboard_markdown.py`.
- Dashboard Settings state and panels moved out of `main.tsx` and
  `settings.tsx` into focused settings components and hooks. Frontend Vitest
  and production build passed from a staged snapshot.

## Progress Update: 2026-05-14 Remaining Debt Split

The remaining high-risk monolith slices were split behind the existing focused
gates without changing HTTP endpoints, SQLite table names, or dashboard
contract names:

- `scripts/dashboard_server.py` is still the public server facade, but artifact
  helpers, git update helpers, fixed-task/current-profile scheduler helpers, and Bot Gateway
  background helpers now live in `scripts/desk_artifacts.py`,
  `scripts/desk_git.py`, `scripts/desk_scheduler.py`, and
  `scripts/desk_bot_gateway_background.py`. A follow-up split moved Telegram credentials,
  notification/AI key settings, source registry/access helpers, source
  assistant planning, and core Desk action execution into
  `desk_credentials.py`, `desk_sources.py`, `desk_source_assistant.py`, and
  `desk_actions.py`. Tests keep re-export/monkeypatch compatibility.
- `scripts/monitor_state.py` remains the public state facade, while DB/schema,
  shared privacy constants, review-card CRUD/actions, alert suppression,
  feedback summaries, and profile patch lifecycle now live in
  `monitor_db.py`, `monitor_common.py`, `review_cards.py`,
  `monitor_alerts.py`, `monitor_feedback.py`, and `profile_patches.py`.
  Dashboard state/run/report/setup projection now lives in
  `dashboard_projection.py`.
- Dashboard Start/Actions and Profiles are now composition entrypoints backed
  by focused subcomponents and pure model modules. Existing helper exports from
  `./actions` and `./profiles` are preserved for tests and callers.
- Sanitizer shared primitives now cover object arrays, local relative paths,
  string records, and source-access summaries. `sanitize/dashboard.ts` is now a
  public facade over dashboard state/review/runs/profiles/summary modules and
  re-exports Desk-owned sanitizer implementations from `sanitize/desk.ts`.
- Focused gates passed: `tests/dashboard`, `tests/monitor_state`, shared
  dashboard/desk/privacy contract fixtures, Dashboard targeted Vitest, and
  Dashboard production build.
- Operator checks passed on 2026-05-14: Docker build/demo/doctor smoke, live
  Telegram status/source-access probe, Windows Task Scheduler install/status/
  remove, Windows Credential Manager write/read/delete, and a structured
  DeepSeek `deepseek-v4-flash` LLM call.

## Progress Update: 2026-05-14 Inbox Split Iteration

The next quality branch continued the UI concentration cleanup without changing
the `InboxView` public props, review action names, or domain filter rules:

- `dashboard/src/components/inbox.tsx` is now a composition facade for inbox
  state, filter selection, and list orchestration.
- Review filter/backlog helpers moved to
  `dashboard/src/components/inbox/filters.tsx`, while preserving the
  `nextNonEmptyReviewFilter` re-export used by existing tests.
- Review-card rendering, lifecycle actions, profile-tuning note behavior,
  report chips, and source refs moved to
  `dashboard/src/components/inbox/review-card.tsx`.
- Setup banner, empty inbox state, first-use checklist, and app-first next-step
  copy moved to `dashboard/src/components/inbox/setup.tsx`.
- Component tests now lock open opportunity actions, source-ref link overflow,
  and empty-state setup recovery details in addition to the existing filter
  behavior tests.
- Focused frontend gates passed: `cd dashboard; npm test -- --run inbox`,
  `cd dashboard; npm test -- --run`, `cd dashboard; npm run build`, and
  `git diff --check`.

## Progress Update: 2026-05-14 Runs Split Iteration

The same quality branch continued the Dashboard UI concentration cleanup on
the Runs surface:

- `dashboard/src/components/runs.tsx` is now a small composition entrypoint for
  run history layout, with public helper exports preserved from the old module.
- Run grouping, outcome classification, compact timeline, recent/archive
  limits, and health-decision model logic moved to
  `dashboard/src/components/runs/model.ts`.
- Evidence group rendering, run rows, count bars, artifact links, and
  diagnostic labels moved to `dashboard/src/components/runs/evidence.tsx`.
- The run health chart and its action buttons moved to
  `dashboard/src/components/runs/health-chart.tsx`; action ids remain
  `sources_import_jobs`, `doctor_jobs`, and `monitor_jobs_dry_run`.
- The no-runs empty state moved to
  `dashboard/src/components/runs/empty-state.tsx`; its action ids remain
  `monitor_jobs_dry_run` and `doctor_jobs`.
- Focused gates passed: `cd dashboard; npm test -- --run runs`,
  `cd dashboard; npm test -- --run`, `cd dashboard; npm run build`,
  `git diff --check`, and a Playwright smoke against Vite with mocked local API
  that opened the Runs tab, verified run health/recovered failure evidence, and
  confirmed a sanitized report link rendered.

## Progress Update: 2026-05-14 Sanitizer Test Split

The large legacy dashboard sanitizer test file was split without changing
runtime sanitizer implementation:

- The old `dashboard/src/domain/sanitize.test.ts` was removed.
- Dashboard-state, inbox, setup, run artifact, optional summary, and profile
  patch/source insight sanitizer coverage moved to
  `dashboard/src/domain/sanitize-dashboard-state.test.ts`.
- Desk action, feedback export/suggestion, action result, and artifact allowlist
  coverage moved to
  `dashboard/src/domain/sanitize-desk-actions-feedback.test.ts`.
- Bot Gateway, bot identity, AI settings, scheduler, notification token, and
  Telegram login status coverage moved to
  `dashboard/src/domain/sanitize-desk-bot-settings.test.ts`.
- Delivery test/chat detection, source import, and saved source library coverage
  moved to
  `dashboard/src/domain/sanitize-desk-source-delivery.test.ts`.
- Cross-entrypoint compatibility coverage for the public, Desk-owned, and
  dashboard re-exported source-import sanitizer moved to
  `dashboard/src/domain/sanitize-entrypoint-compat.test.ts`.
- Focused gates passed: `cd dashboard; npm test -- --run sanitize`,
  `cd dashboard; npm test -- --run`, and `cd dashboard; npm run build`.

## Progress Update: 2026-05-14 Profile Creation Split

The Signal Desk profile creation boundary moved out of the HTTP server facade
without changing the `/api/profiles/create` route contract:

- `scripts/desk_profiles.py` now owns brief/file parsing, profile title/id
  generation, local profile Markdown generation, profile TOML append, and DB
  upsert for newly created profiles.
- `scripts/dashboard_server.py` keeps the public route, loopback/POST
  integrity checks, and monkeypatch-compatible facade re-exports for
  `create_profile_from_brief`, `_profile_*` helpers, `DESK_DELIVERY_TARGET_ID`,
  and `PROFILE_CREATE_*` constants.
- `tests/dashboard/test_profiles.py` now locks the dashboard-server facade
  re-export and patch paths in addition to the existing create-profile endpoint
  behavior.
- Focused gates passed: `python -m pytest tests/dashboard/test_profiles.py -q`,
  `python -m pytest tests/dashboard -q`, targeted `ruff`, `py_compile`, and
  full `python -m pytest -q`.

## Progress Update: 2026-05-14 Monitor Test Split

The large monitor CLI/runtime test file was split by behavior without changing
monitor implementation:

- The old `tests/test_monitor.py` was removed.
- Config defaults, report command/artifact helpers, source freshness, source
  registry filtering, and muted delivery candidate coverage moved to
  `tests/monitor/test_config_helpers.py`.
- Dashboard runtime override coverage for delivery targets, alert mode,
  profile enabled state, and runtime scan/semantic settings moved to
  `tests/monitor/test_runtime_overrides.py`.
- Feedback export CLI coverage moved to
  `tests/monitor/test_feedback_export.py`.
- Prefilter, scan failure sidecars, semantic failure diagnostics, manifest
  projection, and scan-input bypass coverage moved to
  `tests/monitor/test_prefilter_and_manifest.py`.
- Focused gates passed: `python -m pytest tests/monitor -q`,
  `python -m ruff check tests/monitor`, migration count check, and full
  `python -m pytest -q`.

## Progress Update: 2026-05-14 Tgcs CLI Test Split

The large top-level `tgcs` facade test file was split by command behavior:

- The old `tests/test_tgcs_cli.py` was removed.
- Run/demo/init/quickstart/login/doctor coverage moved to
  `tests/tgcs_cli/test_run_demo_init.py`.
- Monitor, dashboard, delivery, feedback, and source command delegation coverage
  moved to `tests/tgcs_cli/test_delegates.py`.
- Schedule preview coverage moved to `tests/tgcs_cli/test_schedule_print.py`.
- The shared `load_tgcs_module` test helper now lives in
  `tests/tgcs_cli/__init__.py`; Bot Gateway facade tests import it from there
  instead of the removed top-level test file.
- Focused gates passed: `python -m pytest tests/tgcs_cli -q`,
  `python -m ruff check tests/tgcs_cli`, migration count check, packaging
  metadata smoke with `tests/tgcs_cli`, and full `python -m pytest -q`.

## Progress Update: 2026-05-14 Monitor Delivery Split

The monitor runner shed the delivery runtime boundary without changing monitor
run behavior:

- `scripts/monitor_delivery.py` now owns profile delivery target selection,
  Signal Desk delivery target runtime overrides, and alert delivery dispatch.
- `scripts/monitor_runner.py` still orchestrates profile runs and imports the
  delivery helpers for the existing call sites.
- `scripts/monitor.py` continues to expose `delivery_targets_for_profile`,
  `apply_delivery_runtime_overrides`, and `run_delivery` as public facade
  functions, now backed by `monitor_delivery`.
- Focused and full gates passed: `python -m pytest tests/monitor -q`,
  targeted `ruff`/`py_compile`, `python -m ruff check .`, and full
  `python -m pytest -q`.

## Progress Update: 2026-05-14 Dashboard Profile Projection Split

The dashboard projection module shed the profile-facing projection boundary
without changing dashboard state contracts:

- `scripts/dashboard_profiles.py` now owns dashboard profile projection,
  profile matching summary extraction from Markdown, display path labels,
  profile report-title lookup, and compact profile/report labels.
- `scripts/dashboard_projection.py` still owns snapshot assembly, run/report
  artifact projection, delivery targets, profile patches, opportunity summary,
  and setup status, while re-exporting the profile helpers for compatibility.
- `tests/monitor_state/test_projection.py` now locks the
  `monitor_state -> dashboard_projection -> dashboard_profiles` facade path,
  including both `monitor_state.PROJECT_ROOT` and `dashboard_projection.PROJECT_ROOT`
  monkeypatch compatibility for profile file lookup.
- Focused and full gates passed: `python -m pytest
  tests/monitor_state/test_projection.py tests/test_dashboard_state_contracts.py
  -q`, `python -m pytest tests/monitor_state -q`, targeted `ruff`/`py_compile`,
  `python -m ruff check .`, and full `python -m pytest -q`.

## Progress Update: 2026-05-14 Monitor Command Execution Split

The monitor runner shed the scan/report command execution boundary without
changing monitor CLI behavior or run manifest contracts:

- `scripts/monitor_execution.py` now owns report/scan/daily-report command
  construction, source-registry argument lookup, latest-manifest pointer writes,
  and the scan-input/prefilter/daily-report execution branches.
- `scripts/monitor_runner.py` still owns profile validation, run directory
  setup, DB writeback, review-card upsert, delivery, manifest assembly, and CLI
  output, while delegating command execution through a typed
  `MonitorCommandResult`.
- `scripts/monitor.py` keeps the public facade and now syncs `PROJECT_ROOT`
  into the execution module; `tests/monitor/test_config_helpers.py` locks
  facade command-helper signatures and patched project-root command paths.
- The CI explicit `py_compile` list now includes `scripts/monitor_runner.py`
  and `scripts/monitor_execution.py`, so syntax coverage follows the split.
- Review found no behavior-equivalence blocker for scan-input, prefilter
  no-match/hit, scan-failure, items-json bypass, or daily-report branches. A
  compatibility concern about public helper signature erosion was addressed by
  restoring explicit keyword-only wrapper signatures.
- Focused and full gates passed: `python -m pytest
  tests/monitor/test_config_helpers.py tests/monitor/test_prefilter_and_manifest.py
  -q`, `python -m pytest tests/monitor tests/test_contract_fixtures.py
  tests/test_dashboard_state_contracts.py -q`, targeted and CI-list
  `py_compile`, `python -m ruff check .`, `python -m pytest -q`, and
  `git diff --check`.

## Progress Update: 2026-05-14 Monitor Manifest Split

The monitor runner shed the run-manifest and monitor-result payload construction
boundary without changing `run_manifest_v1` or `monitor_run_result_v1`:

- `scripts/monitor_manifest.py` now owns run artifact collection, scan/semantic
  manifest sections, `run_manifest_v1` assembly, manifest file writing, and
  `monitor_run_result_v1` data projection.
- `scripts/monitor_runner.py` still owns profile validation, runtime override
  application, command execution, DB writeback, review-card upsert, delivery,
  and CLI success/error envelope routing.
- The CI explicit `py_compile` list now includes `scripts/monitor_manifest.py`.
- Reviewer dispatch was unavailable due account usage limits, so this checkpoint
  uses a degraded reviewer gate rather than claiming independent review. Local
  self-review checked the `monitor.PROJECT_ROOT` patch path: manifest helpers
  use `monitor_config.relative_to_root` and `monitor_artifacts.artifact`, so
  the existing `_monitor_config`/`_monitor_artifacts` sync path still controls
  local path projection.
- Focused and full gates passed: `python -m pytest tests/monitor -q`,
  `python -m pytest tests/monitor tests/test_contract_fixtures.py
  tests/test_dashboard_state_contracts.py -q`, CI-list `py_compile`,
  `python -m ruff check .`, `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Dashboard Opportunity Projection Split

The dashboard projection module shed the opportunity-summary product boundary
without changing dashboard state contracts:

- `scripts/dashboard_opportunities.py` now owns `dashboard_opportunity_summary_v1`
  assembly, high-actionable review-card ranking, decision counts, scan-input
  replay total fallback, and opportunity next-action selection.
- `scripts/dashboard_projection.py` still owns dashboard snapshot assembly,
  run/report artifacts, delivery targets, profile patches, setup status, and
  compatibility re-exports for opportunity helpers.
- `tests/monitor_state/test_projection.py` now locks the
  `monitor_state -> dashboard_projection -> dashboard_opportunities` facade
  path for opportunity summary and next-action helpers.
- The CI explicit `py_compile` list now includes `scripts/dashboard_projection.py`
  and `scripts/dashboard_opportunities.py`.
- Reviewer dispatch is still unavailable due account usage limits, so this
  checkpoint uses a degraded reviewer gate. Focused opportunity tests already
  cover top-item ranking, all-clear cadence, scan-input replay counts, handled
  card exclusion, source-access failure next action, and dashboard-state
  contract projection.
- Focused and full gates passed: `python -m pytest
  tests/monitor_state/test_projection.py tests/test_dashboard_state_contracts.py
  -q`, `python -m pytest tests/monitor_state -q`, targeted and CI-list
  `py_compile`, `python -m ruff check .`, `python -m pytest -q`, and
  `git diff --check`.

## Progress Update: 2026-05-14 Dashboard Setup Projection Split

The dashboard projection module shed the setup-readiness product boundary
without changing dashboard state contracts:

- `scripts/dashboard_setup.py` now owns `dashboard_setup_status_v1`, setup
  check rows, preferred setup profile selection, run-to-profile matching,
  source-attention detection, and the user-facing source-recovery next step.
- `scripts/dashboard_projection.py` still owns dashboard snapshot assembly,
  run/report artifacts, delivery target projection, profile patches, and
  compatibility re-exports for setup helpers.
- `tests/monitor_state/test_projection.py` now locks the
  `monitor_state -> dashboard_projection -> dashboard_setup` facade path for
  setup status and checklist helpers.
- The CI explicit `py_compile` list now includes `scripts/dashboard_setup.py`.
- Reviewer dispatch remained unavailable due account usage limits, so this
  checkpoint uses a degraded reviewer gate. Focused setup tests cover disabled
  profiles, first-run guidance, source-access failure priority, and dashboard
  state contract projection.
- Focused and full gates passed: `python -m pytest
  tests/monitor_state/test_projection.py tests/test_dashboard_state_contracts.py
  -q`, `python -m pytest tests/monitor_state -q`, CI-list `py_compile`,
  `python -m ruff check .`, and `python -m pytest -q`.

## Progress Update: 2026-05-14 Desk Server Selection Split

The dashboard server facade shed the local server selection and health boundary
without changing loopback safety or auto-port behavior:

- `scripts/desk_server_selection.py` now owns `desk_health_v1`, dashboard URL
  normalization, host warnings, compatible existing-instance health checks,
  TCP listener detection, auto-port selection, and loopback address parsing.
- `scripts/dashboard_server.py` keeps the public helpers/constants/class as
  compatibility wrappers and injects `socket`, `urlopen`, `ThreadingHTTPServer`,
  `fetch_compatible_desk_health`, and `is_tcp_port_listening` so existing tests
  and monkeypatch paths still work.
- `tests/dashboard/test_server_selection_security.py` now locks the facade
  constants/class path in addition to the existing loopback, health, auto-port,
  and incompatible-listener security tests.
- The CI explicit `py_compile` list now includes `scripts/desk_server_selection.py`.
- Two reviewer signals found no code-level blocker. The compatibility reviewer
  flagged the expected P1 staging risk while `scripts/desk_server_selection.py`
  was untracked; this checkpoint stages the new module explicitly before commit.
- Focused and full gates passed: `python -m pytest
  tests/dashboard/test_server_selection_security.py tests/dashboard/test_status_endpoints.py
  -q`, `python -m pytest tests/dashboard -q`, CI-list `py_compile`,
  `python -m ruff check .`, `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Desk HTTP Security Split

The dashboard server facade shed the request-integrity and loopback route-gate
helpers without changing POST, Origin/Referer, or sensitive-route behavior:

- `scripts/desk_http_security.py` now owns JSON POST content-type enforcement,
  same-port loopback `Origin`/`Referer` checks, request host-port extraction,
  and sensitive route loopback access gates.
- `scripts/dashboard_server.py` keeps `DashboardHandler` private helper names
  as compatibility wrappers: `_require_post_request_integrity`,
  `_is_loopback_same_port_url`, `_request_host_port`, and
  `_require_loopback_access`.
- The wrappers inject `dashboard_server.is_loopback_address`, preserving the
  old facade monkeypatch path for tests and downstream debugging.
- `tests/dashboard/test_http_security.py` now locks handler delegation and a
  wrong-port loopback `Referer` rejection before action/body execution.
- The CI explicit `py_compile` list now includes `scripts/desk_http_security.py`.
- Reviewer found no loopback-safety or compatibility blocker. The expected P2
  staging risk for the new untracked module is handled by staging the file
  explicitly; the P3 `Referer`/wrong-port test gap was closed before commit.
- Focused and full gates passed: `python -m pytest
  tests/dashboard/test_http_security.py tests/dashboard/test_server_selection_security.py
  -q`, `python -m pytest tests/dashboard -q`, CI-list `py_compile`,
  `python -m ruff check .`, `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Desk Profile Route Split

The dashboard server facade shed the profile mutation and profile patch action
payload helpers without changing route names, response envelopes, or profile
privacy gates:

- `scripts/desk_profile_routes.py` now owns profile alert-mode, enabled,
  runtime-settings, draft-note, matching-preferences, and profile-patch
  apply/revert/replay payload construction.
- `scripts/dashboard_server.py` still owns HTTP dispatch, loopback gates,
  connection lifetime, and response writing. It deliberately keeps request
  shape/private-fragment validation before `_connect()` for fields where unsafe
  input must be rejected before state access.
- The handler passes `dashboard_server.monitor_state` and `PROFILE_*`
  allow-list/length constants into the helper at call time, preserving the old
  monkeypatch surface.
- `tests/dashboard/test_profiles.py` now locks profile route helper patch
  paths and patched draft-note length rejection before state access.
  `tests/dashboard/test_status_endpoints.py` now covers profile-patch apply in
  addition to revert/replay.
- The CI explicit `py_compile` list now includes `scripts/desk_profile_routes.py`.
- Reviewer found no route-equivalence, pre-DB rejection, or monkeypatch blocker.
  The only P1 was the expected untracked new-module staging risk, handled by
  explicitly staging the new module before commit.
- Focused and full gates passed: `python -m pytest
  tests/dashboard/test_profiles.py tests/dashboard/test_status_endpoints.py
  tests/dashboard/test_http_security.py -q`, `python -m pytest
  tests/dashboard -q`, CI-list `py_compile`, `python -m ruff check .`,
  `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Report HTML Link Split

The report HTML renderer shed the untrusted-link and inline-source rendering
helpers without changing generated report behavior:

- `scripts/report_html_links.py` now owns `safe_href`,
  `telegram_handle_to_url`, Telegram Markdown-to-HTML conversion, contact/source
  link rendering, URL field labels, inline value splitting, and shared escaping
  for untrusted report text.
- `scripts/report_html.py` keeps the old helper names as compatibility
  re-exports while staying focused on report card, feedback, diagnostics, and
  template assembly.
- `tests/report/test_html.py` now locks facade helper identity for the moved
  link helpers, unsafe `javascript:` rejection, source handle links, and safe
  Markdown links. Existing report HTML tests still cover attribute injection,
  slash-separated legacy values, custom action labels, apply URLs, contact
  handles, feedback controls, and source-ref scoped raw messages.
- The CI explicit `py_compile` list now includes `scripts/report_html_links.py`.
- Reviewer found no P0/P1 behavior or safety blocker. P2 staging risk for the
  new untracked module is handled by explicitly staging the file; P3 facade
  coverage feedback was addressed by extending the helper identity tests.
- Focused and full gates passed: `python -m pytest
  tests/report/test_html.py tests/report/test_sources.py -q`,
  `python -m pytest tests/report -q`, CI-list `py_compile`,
  `python -m ruff check .`, `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Source Assistant Split

The Desk source registry module shed the free-text and optional LLM source
planning boundary without changing saved-source behavior or external-AI
privacy gates:

- `scripts/desk_source_assistant.py` now owns source-instruction parsing,
  source assistant action classification, resolved-plan cleaning, optional LLM
  source-id planning, source-assistant preview, and confirmed plan application.
- `scripts/desk_sources.py` still owns source registry CRUD, source access
  health/probe/repair, source import, and the old helper names as compatibility
  wrappers.
- `scripts/dashboard_server.py` keeps the same source assistant facade exports.
  The `dashboard_server._source_assistant_llm_plan` monkeypatch path remains
  active through `desk_sources._facade_attr(...)`.
- Existing and new tests lock the privacy gate: no LLM planner call without
  `confirm_external_ai=True`, no planner call when a confirmed local plan is
  already complete, and confirmed AI only fills existing-source operations that
  local parsing could not resolve.
- The CI explicit `py_compile` list now includes
  `scripts/desk_source_assistant.py`.
- Reviewer found no P0/P1 behavior, facade, or privacy blocker. The expected
  untracked-module staging risk is handled by explicitly staging the new file;
  the P3 confirmed-AI/local-plan test gap was closed before commit.
- Focused and full gates passed: `python -m pytest
  tests/dashboard/test_sources.py tests/dashboard/test_desk_actions.py
  tests/test_bot_gateway.py -q`, `python -m pytest tests/dashboard -q`,
  CI-list `py_compile`, `python -m ruff check .`, `python -m pytest -q`, and
  `git diff --check`.

## Progress Update: 2026-05-14 Source Access Split

The Desk source registry module shed the source access health/probe/repair
boundary without changing cached-health, quiet-source, or Telegram-session
semantics:

- `scripts/desk_source_access.py` now owns source access health loading/writing,
  health detail/action-summary projection, per-source probe records, Telethon
  entity/message probing, bounded probe assembly, and cached-health repair
  actions.
- `scripts/desk_sources.py` keeps source registry CRUD/import and the old
  source-access helper names as compatibility wrappers. It injects
  `PROJECT_ROOT`, Telegram session path, credential loading, source-id
  validation, and `_desk_action_result` at call time so dashboard monkeypatch
  paths still work.
- The compatibility wrapper for `_probe_source_access_async` deliberately
  still writes `.tgcs/source-access-health.json`, matching the old helper
  behavior even though the new lower-level async helper is pure-return until
  the public `probe_source_access()` wrapper writes the cache.
- Tests now lock the source-access facade, reason label compatibility,
  structured source-access contract privacy, cached health projection, cached
  repair behavior, and direct async-helper cache writes.
- The CI explicit `py_compile` list now includes
  `scripts/desk_source_access.py`.
- Reviewer found no P0. The P1 untracked-module risk is handled by explicitly
  staging the new module; the P2 async cache-write compatibility finding was
  fixed with a wrapper write and regression test before commit.
- Focused and full gates passed: `python -m pytest
  tests/dashboard/test_desk_actions.py tests/test_desk_source_access_contracts.py
  -q`, `python -m pytest tests/dashboard -q`, CI-list `py_compile`,
  `python -m ruff check .`, `python -m pytest -q`, and `git diff --check`.

## Progress Update: 2026-05-14 Source Library UI Split

The Dashboard Settings saved-source library shed its row and pure model
boundaries without changing API payload shape or source-management behavior:

- `dashboard/src/components/settings/source-library-model.ts` now owns saved
  source filtering, pagination labels, source-yield activity labels, and topic
  edit validation.
- `dashboard/src/components/settings/source-library-row.tsx` now owns per-source
  rendering, pause/use, remove, and topic editor focus/reset/save/cancel
  behavior.
- `dashboard/src/components/settings/source-library-panel.tsx` remains the
  composition entrypoint for summary, topic chips, search, collapsed list gate,
  pagination, and row orchestration. It re-exports the old model helper names
  so `settings.tsx` and existing tests keep the same public import path.
- Focused and full dashboard gates passed: `cd dashboard; npm test -- --run
  settings`, `cd dashboard; npm test -- --run`, `cd dashboard; npm run build`,
  and `git diff --check`.
- Browser smoke was not run for this slice because no CSS/layout or rendered
  text changed and Playwright is not installed in the dashboard workspace. The
  remaining risk is limited to structural module import/re-export behavior,
  covered by Vitest and TypeScript build.

## Progress Update: 2026-05-14 Runtime Settings UI Split

The Dashboard Profiles runtime settings editor was later folded into the
focused profile row boundary while preserving the pure save-state model:

- `dashboard/src/components/profiles/profile-row.tsx` owns rendered profile
  monitoring controls, notification details, and runtime-setting form state.
- `dashboard/src/components/profiles/runtime-settings-model.ts` owns the pure
  runtime-settings helpers, including `runtimeSettingsSaveState`.
- No route/API or profile model shape changed. The existing
  `runtimeSettingsSaveState` public re-export remains unchanged.
- Focused and full dashboard gates passed: `cd dashboard; npm test -- --run
  profiles`, `cd dashboard; npm test -- --run`, `cd dashboard; npm run build`,
  and `git diff --check`.
- Browser/DOM interaction smoke is not covered by the current dashboard test
  stack; this split intentionally avoided changing rendered text, CSS classes,
  input limits, or save/reset ownership.

## Progress Update: 2026-05-14 Bot Gateway Background Split

The Desk scheduler boundary shed the Bot Gateway background/autostart product
surface without changing dashboard actions, Bot Gateway status, or local-first
privacy behavior:

- `scripts/desk_bot_gateway_background.py` now owns Bot Gateway state loading,
  local-first status projection, background status, fixed Bot Gateway argv,
  launchd plist writing, systemd service writing, and confirmed autostart
  install/remove actions.
- `scripts/desk_scheduler.py` remains the fixed-task/current-profile dry-run
  auto-scan scheduler owner and keeps the old Bot Gateway helper names as
  compatibility wrappers.
  Its sync layer deliberately forwards `PROJECT_ROOT`, token status, scheduler
  backend, `_pythonw_entry`, `_run_scheduler_command`, and Bot Gateway constants
  into the new module so the `dashboard_server` monkeypatch surface stays
  effective.
- Regression tests now directly lock the split facade path: patched
  `dashboard_server._pythonw_entry` controls `_fixed_bot_gateway_argv()`, and
  patched `dashboard_server._run_scheduler_command` controls Windows background
  status queries. Existing tests continue to cover token gating, explicit
  confirmation gating, Windows create/run, macOS `KeepAlive`, Linux
  `Restart=on-failure`, and sanitized status output.
- The CI explicit `py_compile` list now includes
  `scripts/desk_bot_gateway_background.py`.
- Focused gates passed: `python -m pytest tests/dashboard/test_scheduler.py
  -q`, targeted `py_compile`, targeted `ruff`, and the mixed Bot Gateway/Desk
  action gate covering scheduler, credentials, action dispatch, and bot
  contracts.

## Progress Update: 2026-05-14 Secret Settings Split

The Desk credentials module shed the local secret-settings boundary without
changing Telegram login, notification target, or settings status contracts:

- `scripts/desk_secret_settings.py` now owns Telegram bot notification token
  status/update, AI provider key status/update, local credential-store labels,
  provider-key validation, and `desk_action_env()` provider-env hydration.
- `scripts/desk_credentials.py` remains the Telegram app credential/login and
  delivery target/chat-detection owner. It keeps the old notification token,
  AI settings, and action-env helper names as compatibility wrappers.
- The wrapper sync layer deliberately keeps `DESK_AI_PROVIDER_CONFIGS`,
  allowed-field constants, and `_utc_now` facade-aware, so dashboard tests and
  future local-provider patches do not silently target the wrong module after
  the split.
- Regression tests now lock a patched dashboard provider config through both
  `desk_ai_settings_status()` and `desk_action_env()`, while existing tests
  continue to cover env-over-local precedence, no token/key echoing,
  save/clear validation, unsupported command-field rejection, and fixture
  contracts.
- The CI explicit `py_compile` list now includes
  `scripts/desk_secret_settings.py`.
- Focused gates passed: credential/settings tests plus Desk settings contract
  tests, targeted `py_compile`, targeted `ruff`, the full dashboard Python
  test directory, and the mixed credential/action/Bot Gateway contract gate.

## Progress Update: 2026-05-14 Delivery Settings Split

The Desk credentials module shed the delivery-target and chat-detection
boundary without changing Telegram login, dry-run notification tests, or
dashboard facade contracts:

- `scripts/desk_delivery_settings.py` now owns default delivery target
  validation, projection, save/test payloads, Telegram bot `getUpdates` chat
  detection, chat-candidate selection, and the no-secret detection result
  payloads.
- `scripts/desk_credentials.py` remains the Telegram app credential/login
  owner. It keeps the old delivery helper names as compatibility wrappers
  because `dashboard_server.py` still exposes them as the public HTTP/test
  facade.
- The wrapper sync layer deliberately keeps delivery target ids, allowed-field
  constants, bot-update timeout, `_utc_now`, and Telegram-session fallback
  facade-aware. This protects existing `dashboard_server` monkeypatch paths
  after the split instead of forcing callers onto the new module immediately.
- Regression tests now lock a patched
  `dashboard_server._detect_chat_id_from_bot_updates` through
  `detect_desk_delivery_chat_id()`, while existing tests continue to cover
  secret/command-field rejection, sanitized target projection, dry-run-only
  send tests, Bot token privacy in `getUpdates`, and Telegram-session fallback.
  A direct-owner regression also verifies the new module can lazy-call the
  credentials session fallback if future code bypasses the facade.
- The CI explicit `py_compile` list now includes
  `scripts/desk_delivery_settings.py`.
- Focused gates passed: credential/settings contract tests, targeted
  `py_compile`, targeted `ruff`, the full dashboard Python test directory,
  and the mixed credential/action/Bot Gateway contract gate.

## Progress Update: 2026-05-14 Telegram Login Split

The Desk credentials facade shed the Telegram app credential/login/session
state machine without changing browser routes or login error semantics:

- `scripts/desk_telegram_login.py` now owns Telegram app credential loading,
  status projection, login-code state, expiration checks, user-facing Telethon
  error mapping, code send/verify flows, cancel-login behavior, and current
  user chat-id lookup.
- `scripts/desk_credentials.py` is now a compatibility facade over Telegram
  login, delivery settings, and local secret settings. It keeps the old helper
  names because `dashboard_server.py` still exposes them as the stable HTTP and
  test facade.
- The wrapper sync layer deliberately keeps `PROJECT_ROOT`, Telegram config
  paths, login-code TTL, provider async hooks, delivery settings hooks, and
  secret-settings constants facade-aware. This preserves existing
  `dashboard_server` monkeypatch behavior while allowing the owner modules to
  stay focused.
- Regression tests continue to cover no API-hash echoing, invalid credential
  rejection, stale code expiry before network, provider-error mapping, login
  HTTP endpoints, delivery session fallback, and settings contracts. Additional
  split regressions now lock the old `desk_credentials` async hook monkeypatch
  surface and the old delivery session-fallback patch surface.
- The CI explicit `py_compile` list now includes
  `scripts/desk_telegram_login.py`.
- Gates passed: credential/settings contract tests, targeted `py_compile`,
  targeted `ruff`, the full dashboard Python test directory, the mixed
  credential/action/Bot Gateway contract gate, full Python tests, full ruff,
  CI-list `py_compile`, and `git diff --check`.

## Progress Update: 2026-05-14 Source Registry Split

The Desk sources facade shed the saved-source registry/import mutation
boundary without changing source access, source assistant, or Settings HTTP
contracts:

- `scripts/desk_source_registry.py` now owns `desk_sources_v1` listing,
  source import preview/write, starter-source import, source enable/disable,
  topic updates, source removal, import payload projection, source-id
  validation, source-topic validation, and pasted-source size/channel limits.
- `scripts/desk_sources.py` remains the compatibility facade for source
  registry, source access, and source assistant helpers. The assistant glue
  payload stays there because it is the bridge between assistant plans and the
  current registry listing, not pure registry ownership.
- The wrapper sync layer deliberately keeps `PROJECT_ROOT`,
  `dashboard_relative_path`, `_utc_now`, import limits, and allowed-field
  constants facade-aware, preserving existing `dashboard_server` monkeypatch
  behavior.
- Regression tests now lock the split facade path, a patched
  `dashboard_server.DESK_SOURCE_IMPORT_MAX_CHANNELS` limit, and patched
  projection helpers for `_utc_now` / `dashboard_relative_path`, while existing
  tests continue to cover no default-registry writes during preview, no
  browser-controlled paths/commands, sanitized registry paths, topic merging,
  source toggles, removal confirmation, source assistant AI gates, and HTTP
  endpoint dispatch.
- The CI explicit `py_compile` list now includes
  `scripts/desk_source_registry.py`.
- Gates passed: source/dashboard action/source-access contract tests, targeted
  `py_compile`, targeted `ruff`, the full dashboard Python test directory,
  Desk contract fixtures, full Python tests, full ruff, CI-list `py_compile`,
  and `git diff --check`.

### 2026-05-14 State Payload Split

The dashboard server facade shed the `/api/state` payload assembly boundary
without changing HTTP routing or the dashboard-server monkeypatch surface:

- `scripts/desk_state_payload.py` now owns `dashboard_state_payload`
  assembly: dashboard snapshot loading, active Desk action injection, and
  cached source-access health detail/action-summary injection into the
  `source_access` setup check.
- `scripts/dashboard_server.py` remains the public HTTP/test facade. Its
  `dashboard_state_payload()` wrapper injects `monitor_state.dashboard_snapshot`,
  `desk_active_actions`, and the `_source_access_*` helper functions at call
  time so existing tests and local callers can still patch the old names.
- Regression tests now cover the owner module directly and the
  dashboard-server facade patch path for snapshot, active actions, cached
  health loading, freshness, detail text, and action-summary helpers.
- The CI explicit `py_compile` list now includes
  `scripts/desk_state_payload.py`.
- Gates passed so far: targeted `ruff`, targeted `py_compile`, state-payload
  focused tests, the full dashboard Python test directory, and Desk/dashboard
  contract fixtures, full Python tests, full ruff, CI-list `py_compile`, and
  `git diff --check`.
- Post-diff review found no `/api/state` behavior, facade monkeypatch, import,
  or CI blocker. Its only P1 was the untracked new-module/test staging risk,
  addressed by explicitly staging both new files before commit.

### 2026-05-14 GET Route Dispatch Split

The dashboard server facade shed the GET route dispatch table without changing
the public HTTP handler, static fallback, or error handling:

- `scripts/desk_get_routes.py` now owns GET routing for
  `/api/desk/health`, Desk actions/status endpoints, `/api/state`, and
  `/artifacts/*`.
- `scripts/dashboard_server.py` still owns `DashboardHandler.do_GET`,
  static serving fallback, and exception mapping. It injects the current
  dashboard-server globals into the GET route owner at call time, preserving
  old monkeypatch paths for health, actions, Telegram status, source listing,
  scheduler status, token status, Bot Gateway status, AI status, state payload,
  loopback gates, and connection cleanup.
- Regression tests now cover direct route-owner state handling, static
  fallback refusal, dashboard-server facade injection for the action and status
  GET helpers, Bot Gateway status connection closing, and artifact route
  loopback/serving behavior.
- The CI explicit `py_compile` list now includes `scripts/desk_get_routes.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused GET/status
  route tests, the full dashboard Python test directory, Desk/dashboard
  contract fixtures, full Python tests, full ruff, CI-list `py_compile`, and
  `git diff --check`.
- Post-diff review found no GET route behavior, facade monkeypatch, exception
  mapping, or import-cycle blocker. Its staging risk for the new module/test
  is handled by explicit staging before commit; its P3 route-coverage feedback
  was addressed with additional status/Bot Gateway/artifact tests.

### 2026-05-14 Settings POST Route Split

The dashboard server facade shed the local settings POST route group without
changing credential, secret, delivery, or Bot identity behavior:

- `scripts/desk_settings_routes.py` now owns POST dispatch for Telegram app
  credentials, Telegram login send/verify/cancel, notification token updates,
  Bot identity apply, AI key settings, and delivery target save/test/chat-id
  detection.
- `scripts/dashboard_server.py` still owns `DashboardHandler.do_POST`, JSON
  POST integrity, request body parsing, exception mapping, and downstream route
  fallback. It injects the current dashboard-server globals into the settings
  route owner at call time, preserving old monkeypatch paths for all settings
  helpers and delivery target helpers.
- Regression tests now cover direct owner routing, unsupported delivery path
  rejection, dashboard-server facade injection for the simple settings helpers,
  delivery save/test connection closing, and delivery chat-id detection without
  opening state.
- The CI explicit `py_compile` list now includes
  `scripts/desk_settings_routes.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused
  settings/credentials/status/security tests, the full dashboard Python test
  directory, Desk/settings/Bot contract fixtures, full Python tests, full ruff,
  CI-list `py_compile`, and `git diff --check`.
- Post-diff review found no settings route behavior, facade monkeypatch,
  request-integrity/error-mapping, or import-cycle blocker. Its staging risk
  for the new module/test is handled by explicit staging before commit; its P3
  delivery test/detect-chat-id coverage feedback was addressed before final
  gates.

### 2026-05-14 Source POST Route Split

The dashboard server facade shed the Desk source POST route group without
changing source registry, source assistant, or source access behavior:

- `scripts/desk_source_routes.py` now owns POST dispatch for source import
  preview, source import apply, starter-source import, source assistant,
  source enable/disable, topic updates, and source removal.
- `scripts/dashboard_server.py` still owns `DashboardHandler.do_POST`, JSON
  POST integrity, body parsing, exception mapping, and downstream route
  fallback. It injects the current dashboard-server globals into the source
  route owner at call time, preserving old monkeypatch paths for all source
  helper functions.
- Regression tests now cover direct owner route matching and source-id
  decoding, non-source fallback, dashboard-server facade injection for source
  action helpers, and source mutation helpers.
- The CI explicit `py_compile` list now includes
  `scripts/desk_source_routes.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused
  source/security tests, the full dashboard Python test directory,
  Desk/source-access/dashboard contract fixtures, full Python tests, full ruff,
  CI-list `py_compile`, and `git diff --check`.
- Post-diff review found no source route behavior, facade monkeypatch, request
  body/error-mapping, source-id decoding, or import-cycle blocker. Its staging
  risk for the new module/test is handled by explicit staging before commit.

### 2026-05-14 Profile POST Route Dispatch Split

The dashboard server facade shed the profile POST route dispatch group without
changing route names, response envelopes, loopback gates, or profile privacy
guards:

- `scripts/desk_profile_post_routes.py` now owns POST dispatch for profile
  creation, profile alert-mode/enabled/runtime-settings/draft-note/matching-
  preferences, and profile patch apply/revert/replay actions.
- `scripts/desk_profile_routes.py` remains the payload/validation helper owner.
  The POST route owner keeps enabled/runtime/draft/matching request-shape and
  private-fragment validation before `_connect()` so invalid profile input does
  not touch dashboard state.
- `scripts/dashboard_server.py` still owns `DashboardHandler.do_POST`, JSON
  POST integrity, body parsing, exception mapping, and downstream route
  fallback. It injects the current dashboard-server globals into the profile
  route owner at call time, preserving old monkeypatch paths for
  `monitor_state`, `desk_profile_routes`, `create_profile_from_brief`, and the
  `PROFILE_*` allow-list/length constants.
- Regression tests now cover direct owner routing, pre-state-access rejection,
  non-profile fallback, dashboard-server facade injection for profile creation,
  and alert-mode success with decoded profile ids.
- The CI explicit `py_compile` list now includes
  `scripts/desk_profile_post_routes.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused
  profile/security tests, the full dashboard Python test directory,
  Desk/settings/Bot contract fixtures, full Python tests, full ruff, CI-list
  `py_compile`, and `git diff --check`.
- Post-diff review found no P0/P1 behavior, facade, loopback, pre-state-access
  validation, or import blocker. Its P2 alert-mode success coverage feedback was
  addressed before final gates; staging risk for the new module/test is handled
  by explicit staging before commit.

### 2026-05-14 Operation POST Route Dispatch Split

The dashboard server facade shed the remaining local operation POST route group
without changing route names, response envelopes, confirmation gates, or local
state mutation behavior:

- `scripts/desk_operation_routes.py` now owns POST dispatch for Desk action
  runs, Git update/pull actions, feedback export/clear/profile-suggestion
  actions, and review-card action/undo routes.
- `scripts/dashboard_server.py` still owns `DashboardHandler.do_POST`, JSON
  POST integrity, body parsing, exception mapping, and downstream route
  fallback. It injects `run_desk_action`, `_git_update_status`,
  `_git_pull_latest`, `DashboardGitError`, `write_feedback_export`, and
  `monitor_state` at call time so old dashboard-server monkeypatch paths remain
  active.
- Regression tests now cover direct owner route matching, decoded Desk action
  ids, feedback export connection cleanup, decoded review-card ids, Git pull
  confirmation rejection before pull, non-operation fallback, and dashboard-
  server facade injection for Desk action/Git helpers.
- The CI explicit `py_compile` list now includes
  `scripts/desk_operation_routes.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused
  operation/security/status/Git tests, the full dashboard Python test
  directory, full Python tests, full ruff, CI-list `py_compile`, and
  `git diff --check`.
- Post-diff review found no P0/P1 behavior, route-order, loopback, Git
  confirmation, connection-closing, or facade monkeypatch blocker. Its P2
  staging/CI risk for the new module/test is handled by explicit staging before
  commit.

### 2026-05-14 Monitor CLI Auxiliary Command Split

The monitor runner shed the auxiliary CLI commands that are not part of the
profile run pipeline:

- `scripts/monitor_cli_commands.py` now owns `init-config`, `feedback-export`,
  and `delivery-test telegram-bot` behavior: starter profile TOML writing,
  reusable feedback JSONL export/recording, and Telegram bot delivery-test
  output/envelope handling.
- `scripts/monitor_runner.py` stays focused on profile run orchestration while
  keeping the old `test_telegram_bot`, `write_default_config`, and
  `export_feedback` function names as compatibility wrappers.
- The wrappers deliberately sync the old `monitor_runner` patch surface into
  the new owner before delegating: `agent_cli`, `delivery`, `monitor_state`,
  `PROFILE_RUN_CONFIG_SCHEMA_VERSION`, `root_path`, and `relative_to_root`.
  This preserves source-checkout tests and local debugging patterns that patch
  `monitor_runner` globals directly.
- Regression tests now cover the monitor facade project-root path for
  `init-config`, missing-chat-id JSON error behavior before delivery, and the
  legacy `monitor_runner.delivery`, schema constant, `root_path`, and
  `relative_to_root` patch surfaces.
- The CI explicit `py_compile` list now includes
  `scripts/monitor_cli_commands.py`.
- Gates passed: targeted `ruff`, targeted `py_compile`, focused
  monitor/tgcs CLI tests, monitor/tgcs/contract mixed tests, full Python tests,
  full ruff, CI-list `py_compile`, and `git diff --check`.
- Post-diff review found no P0/P1 behavior, facade project-root, feedback
  export, delivery-test, or default-TOML blocker. Its P2 compatibility feedback
  about old `monitor_runner` module globals was addressed before final gates.

## Current Debt Snapshot: 2026-05-16

The debt register below remains the long-form reasoning. This table is the
current triage view for what is still real after the later splits:

| Debt | Current Status | Next Useful Slice |
| --- | --- | --- |
| D1. WIP and branch hygiene | Cleared for the known backlog. The current branch is `master`, the worktree is clean, and `origin/master...HEAD` is now `0 0`. | Keep using staged snapshot or clean worktree gates for future slices; do not use mixed-worktree gates as commit proof. |
| D2. Contract sprawl | Materially improved. Shared fixtures now cover the high-risk Python/TypeScript contracts, but `docs/agent-cli-contract.md` is still long. | Keep the contract doc as an index and move new guarantees into fixtures first, prose second. |
| D3. `dashboard_server.py` boundaries | Artifact, git, scheduler, Bot Gateway background, credentials, source, action, profile, state payload, GET, settings/source/profile/operation POST route boundaries are split behind the old facade. The facade is now about `954` lines, and the remaining debt is still compatibility ownership around `DashboardHandler` plus `_sync_desk_scheduler_context()`. | Create a compatibility-owner ledger before removing wrappers. Further backend work should target a named route, injection point, or facade re-export; avoid low-value line shaving. |
| D4. `monitor_state.py` boundaries | Mostly reduced to a `505` line facade. DB/schema, privacy guards, review cards, alerts, feedback, profile patches, and dashboard projection are split, while `tests/monitor_state/test_projection.py` remains a `1020` line behavior lock. | Treat monitor-state projection as a protected contract. Split tests only with a clear owner boundary; do not move projection behavior just to shrink a file. |
| D5. Report pipeline coupling | `report.py` is about `538` lines, but the larger review units are `report_extraction.py` at about `767` lines and `report_sources.py` at about `665` lines. MiniMax/provider routing and semantic batching are real product surfaces. | Treat report extraction, source evidence, and HTML output as separate fixture-backed slices. Do not add another scoring or attribution layer before the current contracts demand it. |
| D6. Dashboard profile/evidence state | Actions, Profiles, Inbox, Runs, the Settings source library, and profile runtime settings are composition entrypoints. Current UI hotspots include `dashboard/src/components/inbox/review-card.tsx` at about `867` lines, `profile-row.tsx` at about `449` lines, and the profile query path through `profile-matching-panel.tsx` and `runtime-settings-model.ts`. | The next UI slice should be driven by a real UX/test gap: review-card evidence/source-preview behavior first, or profile matching/runtime-settings behavior when profile learning changes. |
| D7. Runtime sanitizers | Dashboard sanitizer is now a `14` line facade. Dashboard state sanitizers are split by product area and Desk-owned helpers re-export `sanitize/desk.ts`. The former `1368` line legacy `sanitize.test.ts` is split into focused dashboard-state, Desk action/feedback, Desk bot/settings, Desk source/delivery, and entrypoint-compat files. | Keep these tests close to existing sanitizer modules; avoid adding a second sanitizer implementation. |
| D8. Test concentration | Improved, but the rebuilt graph makes the remaining test-helper hubs visible. `patch`, `load_tgcs_module()`, `BotGatewayTests`, credential/scheduler tests, and `MonitorStateProjectionTests` are high-degree graph nodes; most are test scaffolding, not architecture abstractions. | Keep focused directories. When touching affected owners, reduce helper centrality by moving setup into owner-specific fixtures; do not run a broad test refactor without behavior work. |
| D9. Packaging metadata | Mostly complete for local Python packaging. Build, staged wheel install, `pipx`, `uvx`, and Docker build/demo/doctor smokes passed. | Keep `signal-desk` as a source-checkout launcher until resources are package-safe; re-run Docker when Dockerfile/package-data/dependency metadata changes. |
| D10. Documentation and graph ownership | This file is the debt authority, `docs/testing.md` is command authority, `docs/quality/task-state.md` is compact handoff, dated quality logs are evidence, local ignored `docs/graphify-maintenance/` records are the audit trail for automated doc-debt/Graphify sweeps, `.graphifyignore` is the graph corpus boundary, and `graphify-out/README.md` is the local generated-artifact guide when graph output exists. | Keep graph output advisory. Update this table and `docs/quality/task-state.md` whenever a cleanup slice changes current status; rebuild Graphify after meaningful doc/source boundary changes; keep recurring sweep logs reviewable but outside Git and outside the graph corpus. |

Large current files are still a useful signal, but exact line counts drift too
quickly to be the authority. Treat this list as a dated triage map from the
2026-05-16 workspace, not as a contract:

| Area | Current Hotspot | Why It Matters |
| --- | --- | --- |
| HTTP/Desk compatibility facade | `scripts/dashboard_server.py` | `954` lines. `DashboardHandler`, `_sync_desk_scheduler_context()`, static/artifact serving, exception mapping, and old patch surfaces still bridge communities. Most product helpers are already split, so the remaining debt is migration ownership rather than file size. |
| Review-card evidence UI | `dashboard/src/components/inbox/review-card.tsx` | `867` lines. Owns rendering, actions, source refs, report artifact chips, original-source preview, and source-preview HTML sanitation. This remains the clearest user-facing cleanup candidate. |
| Profile learning and runtime settings | `scripts/profile_patches.py`, `dashboard/src/components/profiles/profile-row.tsx`, `profile-matching-panel.tsx`, `runtime-settings-model.ts` | `profile_patches.py` is `970` lines; the dashboard profile query path now crosses profile row, matching panel, runtime-settings helpers, and shared types. Split only around a tested profile-learning or runtime-settings behavior. |
| Report extraction and source evidence | `scripts/report_extraction.py`, `scripts/report_sources.py`, `scripts/report.py` | `767`, `665`, and `538` lines respectively. These own provider/key routing, JSON repair diagnostics, semantic batching, source evidence, and final report assembly. Keep fixture coverage ahead of refactors. |
| Desk actions/scheduler/Bot Gateway | `scripts/desk_actions.py`, `scripts/desk_scheduler.py`, `scripts/desk_bot_gateway_background.py` | `701`, `906`, and `663` lines. These are fixed-argv and local automation safety surfaces. Preserve allowlists, token/chat gating, and patch-compatible wrappers while migrating. |
| Dashboard contracts/sanitizers/projections | `dashboard/src/domain/sanitize/desk.ts`, `dashboard/src/domain/types.ts`, `dashboard/src/api/client.ts`, `scripts/dashboard_projection.py`, `dashboard/src/domain/projections.ts` | `784`, `684`, `590`, `544`, and `241` lines. `postJson()` and `optionalString()` are high-degree because they are legitimate shared contract/sanitizer surfaces; change them only with fixture-backed contract tests. |
| Focused large tests | `tests/monitor_state/test_projection.py`, `tests/test_bot_gateway.py`, `tests/dashboard/test_credentials_settings.py`, `tests/dashboard/test_scheduler.py`, `tests/monitor/test_prefilter_and_manifest.py` | Large because they protect broad route, projection, gateway, and manifest behavior. The graph's `patch` and `load_tgcs_module()` hubs are still test scaffolding signals, not proof that production architecture is coupled. |
| Graph weak-evidence backlog | `graphify-out/GRAPH_REPORT.md` knowledge gaps | The current public graph snapshot is now synced for 2026-05-16: 3981 nodes, 7410 edges, 33 communities, 376 inferred edges, and refreshed MiniMax semantic coverage. These remain triage prompts only; verify against real files before turning them into debt tickets. |

## Graphify Snapshot Usage

`graphify-out/GRAPH_REPORT.md` exists for the current 2026-05-16 workspace
snapshot and is a useful navigation artifact, but it is not repository truth.
The synced snapshot now has 3981 nodes, 7410 edges, 33 communities,
376 inferred edges, and an LLM-accounted semantic overlay from the MiniMax
OpenAI-compatible China route: 76 semantic nodes, 160 semantic edges,
10230 input tokens, and 5985 output tokens. The refreshed corpus is 340 files
(302 code, 38 docs, about 244331 words), and Graphify still uses directory
fallback clustering at low density (`0.000935347422871706`), so community
boundaries remain inspection hints rather than proof. Daily doc-debt and
Graphify maintenance records live in local ignored
`docs/graphify-maintenance/` files for auditability and are excluded from both
Git and future graph corpora.

Agent rules:

- When `graphify-out` is present, read `graphify-out/README.md` before using
  `GRAPH_REPORT.md` or `graph.json`.
- Use EXTRACTED anchors to decide where to inspect next, then verify with real
  files, docs, commands, tests, issues, or CI output.
- Treat INFERRED edges, LLM-only semantic bridges, test helper hubs,
  low-confidence bridges, and weakly-connected package/config nodes as
  navigation hints rather than facts.
- Do not write graph conclusions directly into memory or docs without checking
  the real source.
- Rebuild the graph after material source/doc changes before relying on
  centrality, community, or weak-node counts.
- Check local ignored `docs/graphify-maintenance/` records for recent automation
  outcomes, but do not treat those records as graph evidence.

Current graph-reading conclusions:

- `DashboardHandler` remains a real bridge because the source confirms it still
  owns HTTP orchestration, static/artifact serving, and exception mapping.
- `postJson()` and `optionalString()` are high-degree because they are shared
  client/sanitizer primitives; do not treat their centrality as debt by itself.
- `patch` and `load_tgcs_module()` are test helper hubs. They should influence
  test-fixture cleanup only when the related owner tests are already changing.
- Low-confidence bridges and weakly-connected nodes belong in a review queue,
  not in durable memory or product claims.
- If a future automation run reports it cannot rewrite public `graphify-out`
  artifacts, treat that as an execution-environment problem first; this repo's
  current `graphify-out` files themselves are directly overwriteable.

## Next Cleanup Plan After Graph Review

The graph report is useful for prioritization, but cleanup should remain
product-risk driven rather than graph-score driven:

1. Frontend-facing slice: review-card evidence/source-preview behavior. Verify
   with Inbox component tests and source-preview sanitation before splitting UI.
2. Profile-learning slice: `profile_patches.py` plus profile row/matching/runtime
   settings. Only split with profile preference or runtime-settings fixtures in
   hand.
3. Report-quality slice: `report_extraction.py`, `report_sources.py`, and
   `report.py`. Keep provider routing, JSON repair, source attribution, and
   semantic batching under focused fixtures before moving code.
4. Compatibility-ledger slice: `dashboard_server.py`, `DashboardHandler`, and
   route/helper re-exports. Write down which tests or downstream callers still
   depend on each facade before removing compatibility paths.
5. Safety automation slice: `desk_actions.py`, `desk_scheduler.py`, and
   `desk_bot_gateway_background.py`. Preserve fixed argv, local-first token/chat
   gating, and patch-compatible wrappers.
6. Test-fixture slice: reduce `patch` and `load_tgcs_module()` centrality only
   inside owner-specific test work. Broad helper cleanup without behavior change
   is currently low value.
7. Documentation slice: keep this file as the current debt authority, keep
   graph output local/advisory, record automated sweeps under local ignored
   `docs/graphify-maintenance/`, and update `docs/quality/task-state.md` after
   each cleanup checkpoint.

## Product Constraints

These constraints must survive every cleanup phase:

1. Local-first defaults stay intact. `.tgcs/`, sessions, bot tokens, credentials,
   raw Telegram text, and output artifacts remain local/private unless an
   explicit product path says otherwise.
2. Telegram Bot and Signal Desk remain allowlist-driven. Browser or Telegram
   input must not become shell, arbitrary argv, raw file path, or command text.
3. Agents use JSON contracts, not human CLI prose. `agent_envelope_v1`,
   `source_registry_v1`, `monitor_run_result_v1`, `run_manifest_v1`, and
   `semantic_items_v1` must remain testable contracts.
4. User-facing dashboard state stays sanitized. Raw scan artifacts and internal
   paths belong in manifests/artifacts, not default dashboard JSON.
5. Compatibility paths remain explicit. Legacy channel lists, deprecated scan
   flags, placeholder-title migration, and old report filenames can be removed
   only after a named migration or owner decision.
6. Future WIP must not be reverted or normalized accidentally. If a later
   cleanup starts from a dirty tree, record ownership first and verify the
   commit candidate from a staged snapshot or clean worktree.

## Non-Goals

- Do not rewrite the project into a new framework.
- Do not introduce a second agent contract layer just to make the docs look
  cleaner.
- Do not split files mechanically without behavior locks.
- Do not make dashboard UI prettier as part of backend cleanup unless a split
  exposes a real UX regression.
- Do not remove legacy behavior just because it is old. Remove it only when the
  product no longer needs the migration path and tests prove the replacement.
- Do not add hosted, team, webhook, Mini App, or public bot infrastructure as
  part of this debt cleanup.

## Recommended Strategy

Use a contract-first, vertical-slice cleanup:

1. Freeze the behavior that users and agents depend on.
2. Split code by ownership boundaries already present in the product.
3. Move one boundary at a time behind tests.
4. Keep public docs and private research/spec notes separated.
5. Treat every removed compatibility branch as a named migration decision.

The risky alternative is a horizontal rewrite, such as "split all helpers out of
`dashboard_server.py` first." That will create many files but not necessarily
better boundaries. The safer path is to split around product responsibilities:
Desk actions, sources, credentials, scheduler, artifacts, monitor state,
report rendering, extraction providers, and dashboard API clients.

## Debt Register

### D1. Checkpoint Hygiene

Evidence:

- Historical quality branch for this register was
  `sapientropic/quality-iteration-spec-20260514`; the current branch is not
  inferred from this debt-register evidence.
- The previously dirty implementation backlog was committed as focused
  checkpoints instead of one mixed cleanup commit.
- Every checkpoint ran `git diff --cached --check` plus a staged snapshot or
  equivalent clean candidate gate before commit.
- Line-ending warnings may still appear on Windows when files are staged, but
  `git diff --check` is the relevant whitespace gate.

Risk:

- A future technical-debt branch could again absorb unrelated packaging,
  dashboard, source, or bot WIP.
- Line-ending churn can hide real diffs.

Cleanup:

- Before any code refactor in a dirty tree, decide whether the dirty work is
  the base, should be staged as the next checkpoint, or should be left alone.
- Run `git diff --check` before and after cleanup.
- Keep spec/doc-only changes separate from behavior changes.

Done when:

- A clean owner decision exists for the next checkpoint scope.
- Technical debt work is verified from a staged snapshot or detached worktree,
  not only from the mixed dirty tree.

### D2. Contract Sprawl Between Docs, Python, And TypeScript

Evidence:

- `docs/agent-cli-contract.md` is the main contract but also contains long
  behavior details for dashboard, monitor, bot, providers, delivery, and
  reports.
- Python emits contract-shaped payloads across `agent_cli.py`,
  `dashboard_server.py`, `monitor.py`, `monitor_state.py`, `report.py`, and
  `source_registry.py`.
- TypeScript has local runtime sanitizers and type definitions in
  `dashboard/src/domain/types.ts`, `sanitize/dashboard.ts`, and
  `sanitize/desk.ts`.

Risk:

- A backend field can change while dashboard sanitizers silently fallback.
- Docs can look authoritative while tests only cover part of the contract.
- Adding a new projection requires editing docs, Python, TypeScript types,
  sanitizers, and tests by hand.

Cleanup:

- Keep `docs/agent-cli-contract.md` as the human-readable contract index.
- Add focused golden contract fixtures under `tests/fixtures/contracts/`.
- For each contract payload, add one backend test that emits the fixture shape
  and one dashboard sanitizer test that accepts it.
- Do not add code generation yet. First prove the existing contract set is
  stable and small enough to benefit from generated types.

Done when:

- Main dashboard API payloads have fixture-backed backend and frontend tests.
- Contract docs point to fixtures instead of repeating every implementation
  detail.
- A field removal or rename fails tests on both sides.

### D3. `dashboard_server.py` Owns Too Many Boundaries

Evidence:

- The file handles HTTP, local action registry, git update checks, Telegram
  login, notification secrets, AI keys, source mutations, source access probes,
  profile creation, scheduler install/remove previews, bot gateway autostart,
  artifact serving, and markdown rendering.

Risk:

- Security boundaries are hard to audit because allowlist logic is mixed with
  presentation and transport logic.
- Tests for one feature import the whole server file.
- New dashboard endpoints are likely to follow the monolith pattern.

Cleanup:

- Extract pure modules first, keeping `DashboardHandler` thin:
  - `scripts/desk_actions.py`: action registry, active action state, action
    result projection.
  - `scripts/desk_sources.py`: source import, assistant plan, saved-source
    mutations, source access health.
  - `scripts/desk_credentials.py`: Telegram credentials, notification tokens,
    AI key status, delivery chat detection.
  - `scripts/desk_scheduler.py`: fixed-task/current-profile dry-run scheduler helpers.
  - `scripts/desk_bot_gateway_background.py`: Bot Gateway status and
    autostart helpers.
  - `scripts/desk_artifacts.py`: artifact path resolution and report/markdown
    rendering.
- Keep external route behavior and endpoint names unchanged.
- Move tests by behavior, not by extracted module name.

Done when:

- `scripts/dashboard_server.py` is mainly route dispatch, loopback checks, and
  server startup.
- Extracted modules can be tested without starting an HTTP server.
- Existing `tests/test_dashboard_server.py` is split into smaller test files
  with the same behavior coverage.

### D4. `monitor_state.py` Mixes Database, Domain, And Projection Logic

Evidence:

- One file owns schema creation, migration helpers, review-card writes,
  alert-event writes, dashboard snapshot projections, feedback export,
  profile patch suggestions, setup status, opportunity summary, source stats,
  and source insights.

Risk:

- SQLite schema changes and dashboard projection changes are difficult to
  review independently.
- Privacy rules such as "do not store raw Telegram text" depend on local helper
  discipline.
- Tests are necessarily huge because many behaviors require the same monolith.

Cleanup:

- Extract without changing table names:
  - `scripts/monitor_db.py`: connection, schema, migrations.
  - `scripts/review_cards.py`: card id, item sanitation, card actions.
  - `scripts/alerts.py`: candidate selection and alert event recording.
  - `scripts/feedback_state.py`: feedback events, exports, profile patch
    suggestion lifecycle.
  - `scripts/dashboard_projection.py`: dashboard snapshot, setup status,
    opportunity summary, source stats, source insights.
- Keep `monitor_state.py` as a compatibility facade during the first phase.
- Add privacy regression tests that attempt to store raw text fields and assert
  they are stripped.

Done when:

- Schema/migration tests do not need projection helpers.
- Projection tests can use in-memory rows/fixtures.
- Raw Telegram text, tokens, sessions, and local absolute paths have explicit
  negative tests.

### D5. `report.py` Couples Extraction, State, Markdown, And HTML

Evidence:

- The file owns prompt message minimization, provider selection, MiniMax and
  DeepSeek quirks, agent extraction request generation, semantic item
  validation, decision memory enrichment, Markdown report construction, and
  HTML card rendering.

Risk:

- Provider-specific fixes can accidentally change rendering.
- Rendering changes can accidentally change extraction prompt shape.
- Prompt minimization and privacy gates are too important to live near HTML
  helpers without focused tests.

Cleanup:

- Extract stable seams in this order:
  - `scripts/report_contracts.py`: semantic item validation, source ref
    validation, extraction request schema helpers.
  - `scripts/extraction_provider.py`: provider selection, request payloads,
    response parsing, provider usage metadata.
  - `scripts/report_markdown.py`: Markdown generation.
  - `scripts/report_html.py`: HTML report rendering and safe links.
- Keep command-line flags and JSON envelope behavior unchanged.
- Preserve existing comments around prompt minimization and provider quirks.

Done when:

- Extraction prompt snapshot tests are independent from HTML rendering tests.
- Provider routing tests do not import HTML templates.
- Report rendering can be changed without touching provider code.

### D6. Dashboard Root And Settings Components Are Too State-Heavy

Evidence:

- `dashboard/src/main.tsx` owns most mutation handlers and status refresh logic.
- `dashboard/src/components/settings.tsx` owns source library, source import,
  notification token, bot gateway, delivery target, AI keys, source yield, and
  source insights.

Risk:

- UI changes require reading the entire dashboard state machine.
- Adding one settings panel increases root component state and prop drilling.
- Tests are likely to become broad render checks instead of focused behavior
  tests.

Cleanup:

- Extract root mutation groups into hooks:
  - `use-feedback-actions.ts`
  - `use-profile-actions.ts`
  - `use-delivery-settings.ts`
  - `use-source-settings.ts`
  - `use-repository-actions.ts`
- Split Settings into focused panels:
  - `settings/notifications-panel.tsx`
  - `settings/source-library-panel.tsx`
  - `settings/source-import-panel.tsx`
  - `settings/ai-panel.tsx`
  - keep `learning-panel.tsx` as the existing good pattern.
- Keep visual layout stable until behavior tests pass.

Done when:

- `main.tsx` is mostly app composition, selected tab state, and top-level data
  loading.
- Each settings panel has focused tests for labels, disabled states, and action
  callbacks.
- No panel needs to know every dashboard mutation.

### D7. Runtime Sanitizers And Type Shapes Are Duplicated

Evidence:

- `sanitize/dashboard.ts` and `sanitize/desk.ts` share helper patterns and some
  overlapping payload concepts.
- `types.ts` is the central frontend type file, but runtime validation lives in
  large separate sanitizer files.

Risk:

- A new field can be sanitized in one API path but ignored in another.
- Runtime fallbacks can hide backend contract drift.

Cleanup:

- Extract shared sanitizer primitives into `dashboard/src/domain/sanitize/shared.ts`.
- Keep endpoint-specific sanitizers separate where payloads are genuinely
  different.
- Add "unexpected field" tests only for payloads where extra data could leak
  internal paths, commands, tokens, or raw text.
- [⚠️ 需确认] Decide later whether generated types are worth it after fixture
  coverage exists.

Done when:

- Shared helpers are not copy-pasted.
- Contract fixture tests cover both dashboard state and desk action payloads.
- Sanitizers remain conservative about unsafe fields.

### D8. Tests Are Strong But Too Concentrated

Evidence:

- `tests/test_dashboard_server.py` has 2648 lines.
- `tests/test_monitor_state.py` has 2344 lines.
- `tests/test_report.py` has 1246 lines.
- Current full Python suite takes about 95 seconds locally.

Risk:

- Large test files mirror large implementation files and slow targeted review.
- New contributors may run only broad suites because focused entry points are
  hard to discover.

Cleanup:

- Split tests by product boundary:
  - dashboard actions
  - dashboard credentials
  - dashboard source operations
  - dashboard scheduler
  - dashboard artifacts
  - monitor schema
  - review cards
  - feedback/profile patch
  - source stats/insights
  - report extraction contract
  - report rendering
- Keep test names behavior-oriented.
- Keep `docs/testing.md` as the single command index for fast targeted gates,
  staged snapshots, and clean worktree full gates.

Done when:

- Each extracted module has a matching focused test file.
- A developer can run a sub-2-minute full local gate and smaller sub-10-second
  boundary gates.
- CI still runs the full suite.

### D9. Packaging And Dependency Metadata

Evidence:

- `pyproject.toml` contains package metadata, optional dependency groups,
  package data, and the `tgcs` console script.
- `MANIFEST.in`, `Dockerfile`, package resource `__init__.py` files, and
  `tests/test_packaging_metadata.py` are committed.
- `requirements*.txt` still exist as compatibility/development inputs.
- `signal-desk` remains a source-checkout launcher until dashboard/templates
  resources are fully package-safe.
- Docker build/demo/doctor smoke passed locally on 2026-05-14 after Docker
  Desktop became reachable.

Risk:

- Install support can be overstated if Docker or package-data smokes are not
  kept in the release checklist.
- CI can pass while launchers, package metadata, and bundled resources drift.

Cleanup:

- Keep documenting supported entry points and compatibility aliases:
  `tgcs`, `tgcs.bat`, `signal-desk`, `Signal Desk.bat`, and direct scripts.
- Add smoke tests for facade commands that do not require credentials:
  `tgcs demo`, `tgcs quickstart jobs`, `tgcs doctor --format json` with a temp
  registry/profile where possible.
- Re-run the packaging metadata smoke in `docs/testing.md` after dependency,
  launcher, package-data, or Dockerfile changes.

Done when:

- Launchers are thin wrappers around one Python facade.
- Local build, staged wheel install, `pipx`, and `uvx` smokes pass.
- Docker smoke passes in an environment with a reachable Docker daemon.
- Install checks are tested without Telegram credentials.
- Packaging decisions are explicit in roadmap/spec docs.

### D10. Documentation Needs A Cleaner Ownership Model

Evidence:

- `README.md` is the public story.
- `ROADMAP.md` includes market positioning, phase plans, and product principles.
- `SKILL.md` is the agent workflow.
- `docs/agent-cli-contract.md` is a long contract and implementation boundary
  document.
- `docs/testing.md` is the canonical local command index.
- `docs/quality/2026-05-13-tech-debt-iteration-log.md` is a large historical
  implementation log; it should not be used as current state.
- `docs/quality/task-state.md` is the compact current handoff.
- `graphify-out/` is gitignored generated evidence. When it exists locally,
  `graphify-out/README.md` is the first reading guide for agents, and
  `.graphifyignore` is the trackable corpus boundary.
- `docs/graphify-maintenance/` is the local ignored audit trail for recurring
  doc-debt/Graphify sweeps and is deliberately excluded from both Git and the
  graph corpus.
- Local ignored UX/research artifacts still exist under ignored doc paths, but
  they are not stable public docs.

Risk:

- Public docs, agent contracts, temporary design notes, and private research can
  start repeating each other.
- Future agents may follow an outdated doc because it looks authoritative.

Cleanup:

- Keep one authority per topic:
  - Public user path: `README.md` and `README.zh-CN.md`.
  - Product direction: `ROADMAP.md`.
  - Agent execution: `SKILL.md`.
  - JSON contracts: `docs/agent-cli-contract.md`.
  - Local verification commands: `docs/testing.md`.
  - Technical-debt status: this file.
  - Current quality handoff: `docs/quality/task-state.md`.
  - Historical quality evidence: `docs/quality/*-iteration-log.md`.
  - Internal implementation specs: gitignored `docs/internal/specs/`.
  - Local ignored Graphify maintenance audit records:
    `docs/graphify-maintenance/`.
  - Graph corpus boundary: `.graphifyignore`.
  - Local generated graph guidance, when present: `graphify-out/README.md`.
- Keep `docs/internal/specs/INDEX.md` as the private index authority for active
  specs. Public docs may link to stable summaries, but must not mirror internal
  implementation details.
- When product reviews create implementation choices, add or update the active
  internal spec first. Keep `ROADMAP.md` to phase direction and stable product
  boundaries so implementation contracts do not spread across public docs.
- Keep temporary quality logs labeled as historical evidence or move them out of
  tracked docs once they are no longer needed for handoff.

Done when:

- New agents can find the right source in under one minute.
- No full contract is duplicated in multiple docs.
- Draft specs have a clear status and owner.
- Generated graph artifacts are clearly marked as advisory navigation evidence.
- Daily sweep records are reviewable locally without entering Git or becoming
  graph source material.

## Execution Plan

### Phase 0: Stabilize The Baseline

Purpose: avoid cleaning debt on top of ambiguous WIP.

Status: completed for the 2026-05-14 checkpoint backlog. Repeat these tasks if
future cleanup starts from another dirty tree.

Tasks:

1. Decide what to do with current dirty WIP.
2. Run and record the full local gate from `docs/testing.md`.
3. Record the exact branch, dirty files, and untracked files in the first
   cleanup PR/commit notes.
4. Do not refactor behavior in this phase.

Exit criteria:

- Owner agrees on the baseline branch.
- Quality gates pass or failures are documented as pre-existing.
- There is no accidental ownership of unrelated WIP.

### Phase 1: Lock Contracts And Privacy Boundaries

Purpose: make future splits safe.

Tasks:

1. Add backend fixture tests for core JSON payloads:
   - `agent_envelope_v1`
   - `desk_health_v1`
   - `desk_actions_v1`
   - `desk_action_result_v1`
   - `desk_sources_v1`
   - `monitor_run_result_v1`
   - `run_manifest_v1`
   - `review_card_v1`
   - `semantic_items_v1`
2. Add frontend sanitizer tests using the same fixture payloads.
3. Add privacy negative tests for dashboard state, review cards, feedback
   export, bot responses, and artifacts.
4. Update `docs/agent-cli-contract.md` to point to fixture coverage and reduce
   repeated implementation prose where safe.

Exit criteria:

- Contract fixture changes require both backend and frontend review.
- Unsafe fields fail tests before UI rendering.

### Phase 2: Split Python Backend By Product Boundary

Purpose: reduce monolith risk without changing behavior.

Order:

1. Extract artifact serving and markdown rendering from `dashboard_server.py`.
2. Extract credentials and local secret status from `dashboard_server.py`.
3. Extract source operations and source access health from `dashboard_server.py`.
4. Extract fixed action registry and active-action state from
   `dashboard_server.py`.
5. Extract scheduler/bot gateway autostart helpers.
6. Split `monitor_state.py` into database, review cards, feedback, alerts, and
   projections.
7. Split `report.py` into contracts, provider/extraction, Markdown, and HTML.

Rules:

- Each extraction starts with tests around the current behavior.
- The public CLI and route names do not change.
- Compatibility facades can stay temporarily, but every facade must have a
  removal or stabilization decision.

Exit criteria:

- The three largest Python files are reduced enough that their top-level purpose
  is obvious from the imports and exported functions.
- Existing tests still pass.
- At least one focused test file exists for each extracted boundary.

### Phase 3: Split Dashboard State And Settings

Purpose: make UI work less global.

Order:

1. Extract root mutation hooks from `main.tsx`.
2. Split Settings into focused panels.
3. Extract shared sanitizer helpers.
4. Keep layout and visual design stable unless a test exposes a real issue.

Rules:

- Do not change API payload shape in this phase.
- Do not widen dashboard access to commands, paths, tokens, raw messages, or
  argv.
- Keep tests near the component or domain module they protect.

Exit criteria:

- `main.tsx` reads as app composition, not a command center.
- `settings.tsx` no longer owns every settings surface.
- Dashboard tests and build pass.

### Phase 4: Packaging And Launcher Convergence

Purpose: reduce setup drift after internals are safer.

Tasks:

1. Define canonical local entry points.
2. Add smoke tests for credential-free facade paths.
3. Move packaging metadata into `pyproject.toml` only after facade behavior is
   locked.
4. Keep Windows/macOS/Linux launchers as thin wrappers.
5. Document `pipx`/`uvx`/Docker as future packaging tracks, not implied current
   support.

Exit criteria:

- A technical user has one documented CLI entry point and one documented desktop
  entry point.
- Launcher tests catch line-ending and wrapper drift.

### Phase 5: Documentation And Archive Cleanup

Purpose: prevent documentation debt from recreating technical debt.

Tasks:

1. Add or update a spec index.
2. Ensure `README.md`, `ROADMAP.md`, `SKILL.md`, and
   `docs/agent-cli-contract.md` each own one topic.
3. Move temporary implementation notes out of public docs when they are no
   longer active.
4. Add a short testing/quality-gate doc if command discovery remains noisy.

Exit criteria:

- Active specs are easy to find.
- Deprecated or temporary notes have a status.
- No doc repeats a full contract owned elsewhere.

## Quality Gates

Canonical command groups live in `docs/testing.md`. Use that file for focused
contract/privacy gates, medium v0.5 backend gates, full local gates, staged
snapshot verification, launcher checks, and dashboard visual audit triggers.

## Rollback Strategy

- Keep each extraction in a small commit or PR.
- Preserve compatibility imports until consumers are moved.
- If a split causes regressions, revert that split only; contract fixture tests
  should remain.
- Do not combine behavior changes and file moves unless the behavior change is
  required to make the move safe.

## Acceptance Criteria

The technical-debt cleanup is complete when:

1. Core JSON contracts have backend and frontend fixture coverage.
2. `dashboard_server.py`, `monitor_state.py`, and `report.py` have clear module
   boundaries and no longer own unrelated product surfaces in one file.
3. `main.tsx` and `settings.tsx` no longer centralize most dashboard mutation
   logic.
4. Privacy and safety boundaries have negative tests.
5. Launchers and packaging docs point to one canonical facade.
6. Public docs, agent docs, roadmap, and specs have non-overlapping authority.
7. Full Python and dashboard gates pass.

## Owner Decisions Still Open

Resolved historical decisions:

- The current cleanup target is v0.5 release hardening unless the owner changes
  the roadmap priority.
- Core contract/privacy fixtures, dashboard route splits, Docker smoke, and
  package metadata smokes have already been proven enough to stop treating them
  as open planning questions.
- Implementation specs remain under gitignored `docs/internal/specs/`; the
  private `INDEX.md` there is the authority for active private specs.

Still open:

1. [⚠️ 需确认] Should behavior-changing fixes be allowed during cleanup?
   Recommendation: only when a test exposes a real privacy, contract, setup, or
   first-use product bug; otherwise keep refactor-only.
2. [⚠️ 需确认] What is the acceptable local Python test runtime after cleanup?
   Recommendation: keep the full suite under two minutes, and maintain smaller
   focused boundary gates under ten seconds where practical.
3. [⚠️ 需确认] Which packaging target matters first after local Python, `pipx`,
   `uvx`, and Docker smokes passed? Recommendation: make Signal Desk resources
   package-safe before evaluating heavier desktop packaging.
4. [⚠️ 需确认] When can old compatibility paths be removed? Recommendation:
   keep them until at least one release after a documented migration path.
5. [⚠️ 需确认] Should `.graphifyignore` remain a tracked graph boundary
   contract? Recommendation: track it, because the graph corpus boundary affects
   future agent evidence quality and contains no private runtime data.
