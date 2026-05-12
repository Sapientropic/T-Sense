# 2026-05-13 Technical Debt Quality Iteration Log

## Run Contract

- Mode: Standard quality iteration.
- Run shape: continuous until the stop condition.
- Stop condition: keep opening useful, verifiable slices until 2026-05-13
  14:00 +08:00, then do final verification, artifact hygiene, and handoff.
- Priority: v0.5 hardening first.
- Behavior fixes: allowed when they address real contract, privacy, setup, UX,
  or reliability issues found during cleanup.
- Branch: `sapientropic/v05-hardening-tech-debt-20260513`, created from the
  current `sapientropic/issue-5-bot-lifecycle` worktree state.
- Commit policy: commit meaningful checkpoints for rollback; do not commit
  unrelated noise just to create activity.
- Subagent policy: use subagents for substantial independent audit or
  implementation slices, not for tiny local edits.

## Baseline Facts

- Current local time at startup: 2026-05-13 05:55 +08:00.
- Quality spec source: `docs/technical-debt-cleanup-spec.md`.
- Current branch began dirty with existing bot/dashboard WIP. This run must not
  revert those changes.
- Most recent pre-run gates from the spec-writing slice:
  - Python: `429 passed, 2 skipped, 64 subtests passed`.
  - Dashboard: `12` Vitest files, `106` tests passed.
  - Dashboard build: passed.
  - Ruff: passed.
  - `git diff --check`: no whitespace errors, but pre-existing CRLF/LF warnings
    remain on several WIP files.

## Slice 0: Startup And Coordination

Status: completed.

Actions:

- Loaded `$quality-iteration`.
- Recalled project memory. Memory was available through the shadow path; daemon
  was degraded/unavailable. Current files and command output remain authority.
- Created branch `sapientropic/v05-hardening-tech-debt-20260513`.
- Established desktop task binding for a conservative first write scope.
- Started two read-only explorer reviewers:
  - Backend/contract/privacy audit.
  - Dashboard sanitizer/state/UX hardening audit.

Verification:

- `Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"` returned
  `2026-05-13 05:55:22 +08:00`.
- Branch command returned `sapientropic/v05-hardening-tech-debt-20260513`.

Reviewer Gate:

- Pending. Two read-only reviewer agents are running.
- Gate status is currently degraded until reports are received and triaged.

Residual Risk:

- Repo index in the desktop route is stale, so file-scope claims are used as
  coordination, not as proof of impact analysis.
- Current WIP may contain behavior already in progress. New changes must be
  isolated by diff and commits.

## Slice 1: Shared Review-Card Privacy Fixture

Status: completed.

Actions:

- Added `tests/fixtures/contracts/review-card-privacy-item.json` as a shared
  Python/Dashboard privacy fixture.
- Added `tests/test_contract_privacy_fixtures.py`.
- Added `dashboard/src/domain/contract-privacy-fixtures.test.ts`.
- Hardened `scripts/monitor_state.py` review-card item projection to strip
  control-plane fields, credentials, local paths, argv, command strings, and raw
  transport/debug fields before they can enter SQLite-backed dashboard surfaces.

Verification:

- `python -m pytest tests/test_contract_privacy_fixtures.py tests/test_monitor_state.py::MonitorStateTests::test_review_card_item_sanitizer_strips_raw_media_text_fields`
  passed: `2 passed`.
- `python -m pytest tests/test_monitor_state.py` passed: `66 passed`.
- `npm test -- contract-privacy-fixtures` passed: `1` file, `1` test.
- `npm test -- sanitize contract-privacy-fixtures` passed: `2` files, `27`
  tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Backend reviewer returned. It agreed contract fixtures should precede broad
  module splits and raised a P0 finding: `agent_extraction_request_v1` currently
  appears to use full scan metadata where the contract requires a minimized
  projection.
- Dashboard reviewer is still pending.

Residual Risk:

- `scripts/monitor_state.py` already contained uncommitted lifecycle WIP before
  this slice. Stage/commit must isolate only this slice's hunks or explicitly
  label any broader checkpoint.

Next:

- Fix the P0 `agent_extraction_request_v1` minimized metadata boundary and add
  fixture-backed tests.

## Slice 2: Agent Extraction Request Minimal Metadata

Status: completed.

Actions:

- Added `tests/fixtures/contracts/agent_extraction_request_v1.minimal.json`.
- Added `tests/test_report_contracts.py`.
- Changed `scripts/report.py` so `agent_extraction_request_v1.scan_meta` uses
  the same minimized `extraction_prompt_meta()` projection as the LLM prompt.

Verification:

- `python -m pytest tests/test_report_contracts.py tests/test_agent_semantic_fallback.py tests/test_report.py::ReportTests::test_extraction_prompt_uses_cache_friendly_scan_metadata`
  passed: `7 passed`.
- Re-ran the review-card privacy fixture smoke:
  `python -m pytest tests/test_contract_privacy_fixtures.py tests/test_monitor_state.py::MonitorStateTests::test_review_card_item_sanitizer_strips_raw_media_text_fields`
  passed: `2 passed`.

Reviewer Gate:

- Backend reviewer P0 is addressed.
- Dashboard reviewer returned with P1 findings around `/api/state` /
  `/artifacts/*` loopback exposure, API client contract drift, stale duplicate
  sanitizer implementations, artifact path acceptance, and delivery `chat_id`
  breadth.

Residual Risk:

- Full Python suite has not been re-run after Slice 2 yet. Targeted contract
  paths pass.

Next:

- Commit a passing checkpoint, then take the next large hardening slice from
  the reviewer P1 list.

## Slice 3: Dashboard Loopback Boundary

Status: completed.

Actions:

- Added loopback guards to `GET /api/state` and `GET /artifacts/*`.
- Added loopback guards to local mutation endpoints:
  - `POST /api/git/pull-latest`
  - `POST /api/feedback/export`
  - `POST /api/feedback/clear`
  - `POST /api/review-cards/*/action`
  - `POST /api/review-cards/*/undo`
  - `POST /api/profile-patches/*/apply`
  - `POST /api/profile-patches/*/revert`
- Added negative HTTP handler tests proving non-loopback requests are rejected
  before DB connections, artifact serving, or mutation functions are reached.

Verification:

- `python -m pytest tests/test_dashboard_server.py -k "loopback or state_and_artifact or local_state_mutation or get_state_returns_json_error or profile_patch_revert_endpoint or feedback_profile_suggestions"`
  passed: `12 passed, 120 deselected`.
- `python -m pytest tests/test_dashboard_server.py` passed: `132 passed`.

Reviewer Gate:

- Addresses Rawls P0/P1 local mutation endpoint loopback concern for the listed
  endpoints.
- Addresses Cicero P1 `/api/state` and `/artifacts/*` exposure concern for
  non-loopback clients.

Residual Risk:

- This intentionally makes state and report artifacts localhost-only. Default
  product launch is local Signal Desk; remote dashboard hosting remains outside
  the current v0.5 local contract.

Next:

- Commit this verified dashboard boundary checkpoint, then continue with API
  client contract drift and stale sanitizer duplication.

## Slice 4: Dashboard API Contract Drift

Status: completed.

Actions:

- Added client-side top-level contract assertions for:
  - `loadDashboardState`: requires `dashboard_state_v1` plus required array
    fields before sanitizer fallback can run.
  - `loadDeskActions`: requires `desk_actions_v1` plus an `actions` array.
- Added Vitest coverage proving malformed OK payloads throw visible contract
  errors instead of becoming empty state or empty controls.

Verification:

- `npm test -- client` passed: `1` file, `5` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses Cicero P1 API client contract drift finding for the two highest
  impact entrypoints.

Residual Risk:

- This keeps sanitizer functions permissive for local partial payload reuse.
  Only network entrypoints now fail fast on malformed top-level contracts.

Next:

- Continue with stale duplicate sanitizer drift and source-import/action result
  fixture coverage.

## Slice 5: Source Import Sanitizer Drift

Status: completed.

Actions:

- Added `tests/fixtures/contracts/desk_source_import_result_v1.json`.
- Added sanitizer coverage proving the public barrel, the canonical desk module,
  and the legacy dashboard module preserve the same `desk_source_import_result_v1`
  semantics for `removed_count`, `enabled_count`, `disabled_count`, `action`, and
  `llm_used`.
- Changed `sanitize/dashboard.ts` source-import sanitizer to delegate to the
  canonical desk sanitizer instead of keeping a stale implementation.

Verification:

- `npm test -- sanitize` passed: `1` file, `27` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses the concrete stale sanitizer drift called out in Cicero P1. Broader
  shared primitive extraction remains intentionally deferred until more fixture
  coverage is in place.

Residual Risk:

- Other legacy Desk sanitizer exports still exist in `sanitize/dashboard.ts`;
  they are not used by the barrel, but should be either delegated or deleted in
  a later structural cleanup once fixtures cover them.

Next:

- Commit this sanitizer drift checkpoint, then continue with artifact path
  validation and/or feedback export path hardening.

## Slice 6: Report Artifact Path Projection

Status: completed.

Actions:

- Added backend report-artifact path validation before projecting run artifacts
  into `dashboard_state_v1`.
- Added frontend run artifact path validation before rendering report links.
- Kept resolver/projection/sanitizer naming compatible with existing
  `signal-report` and `signal-brief` filenames.
- Added negative tests for absolute paths, traversal, raw/non-report artifacts,
  and a positive resolver test for named brief files.

Verification:

- `python -m pytest tests/test_monitor_state.py::MonitorStateTests::test_dashboard_report_artifact_rejects_non_report_paths tests/test_monitor_state.py::MonitorStateTests::test_dashboard_runs_prefer_html_report_artifact_for_click_target tests/test_monitor_state.py::MonitorStateTests::test_dashboard_runs_project_report_artifact_without_full_manifest`
  passed: `3 passed`.
- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_resolve_run_artifact_allows_named_brief_file tests/test_dashboard_server.py::DashboardServerGitTests::test_resolve_run_artifact_rejects_non_report_html`
  passed: `2 passed`.
- `npm test -- sanitize` passed: `1` file, `27` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses Cicero P1 artifact path concern across backend projection, server
  resolver, and frontend sanitizer.

Residual Risk:

- This is path-shape validation, not content inspection. It assumes report
  artifact writers only label report HTML/Markdown as report artifacts.

Next:

- Commit this artifact hardening checkpoint, then continue with feedback export
  path hardening and broader verification.

## Slice 7: Feedback Export Path Hardening

Status: in progress.

Actions:

- Added a dashboard-only feedback export target resolver that keeps export
  writes inside the project root before recording or returning the path.
- Tightened feedback export sanitizers to reject absolute paths, traversal,
  URL-shaped paths, and control characters while keeping existing relative
  output paths compatible.
- Delegated the legacy dashboard feedback export sanitizer to the canonical
  Desk sanitizer so both entrypoints share the same path contract.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_write_feedback_export_writes_note_free_dashboard_jsonl tests/test_dashboard_server.py::DashboardServerGitTests::test_write_feedback_export_defaults_to_grouped_feedback_file tests/test_dashboard_server.py::DashboardServerGitTests::test_write_feedback_export_rejects_path_outside_project`
  passed: `3 passed`.
- `npm test -- sanitize` passed: `1` file, `27` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses the dashboard feedback export path leakage concern without changing
  the normal `output/feedback/review-feedback.jsonl` workflow.

Residual Risk:

- CLI `tgcs feedback export --output ...` still permits explicit paths because
  it is a local CLI operation. This slice only hardens the dashboard surface.

Next:

- Commit this checkpoint, then run a wider backend/frontend verification pass
  before choosing the next high-risk v0.5 hardening target.

## Slice 8: Desk Action Artifact Contract

Status: in progress.

Actions:

- Added a dashboard artifact resolver that still supports run report artifacts
  and restores safe `output/demo-report.html` serving for the offline demo.
- Tightened Desk action artifact projection so action results only expose
  openable report HTML/Markdown paths, not feedback JSONL, traversal, absolute
  local paths, or URLs.
- Delegated the legacy dashboard Desk action result sanitizer to the canonical
  Desk sanitizer so artifact-link semantics cannot drift between entrypoints.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_run_desk_action_ignores_arbitrary_command_payload_and_uses_fixed_entry tests/test_dashboard_server.py::DashboardServerGitTests::test_run_desk_action_only_returns_openable_report_artifacts tests/test_dashboard_server.py::DashboardServerGitTests::test_serve_markdown_artifact_over_http_as_rendered_html tests/test_dashboard_server.py::DashboardServerGitTests::test_serve_html_report_artifact_injects_mobile_patch tests/test_dashboard_server.py::DashboardServerGitTests::test_serve_artifact_allows_demo_report_html tests/test_dashboard_server.py::DashboardServerGitTests::test_serve_artifact_rejects_raw_scan_over_http_handler`
  passed: `6 passed`.
- `npm test -- sanitize` passed: `1` file, `27` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Fixes the mismatch introduced by stricter `/artifacts/*` serving: JSONL paths
  are no longer rendered as "Open result" links, while demo/report HTML remains
  openable.

Residual Risk:

- This still intentionally treats artifact serving as report-only. Raw exports
  remain local file paths for CLI/manual workflows rather than browser-opened
  artifacts.

Next:

- Commit this checkpoint, then run wider regression before selecting the next
  v0.5 hardening target.

## Slice 9: Feedback Summary Legacy Path Hardening

Status: in progress.

Actions:

- Added backend projection cleanup for `feedback_summary.last_export_path` so
  legacy absolute, traversal, URL-shaped, or control-character paths degrade to
  the default relative feedback export path.
- Added frontend sanitizer cleanup for the same field so malformed dashboard
  state cannot surface old local paths in Settings.

Verification:

- `python -m pytest tests/test_monitor_state.py::MonitorStateTests::test_feedback_summary_tracks_changes_since_last_export tests/test_monitor_state.py::MonitorStateTests::test_feedback_summary_masks_legacy_unsafe_export_path`
  passed: `2 passed`.
- `npm test -- sanitize` passed: `1` file, `27` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Completes the feedback export hardening path by covering historical DB rows,
  not only new dashboard exports.

Residual Risk:

- The CLI export command still prints explicit local output paths by design.
  This slice only controls dashboard state and UI sanitizer surfaces.

Next:

- Commit this checkpoint, then run wider regression and continue with the next
  contract/privacy hardening target.

## Slice 10: Desk Health URL Trust Boundary

Status: in progress.

Actions:

- Tightened compatible Desk health checks so a reused local instance must report
  an HTTP loopback URL on the same port when it includes a URL.
- Changed auto-port reuse to open the URL computed from the requested local
  host/port instead of trusting the health payload's `url` field.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_select_dashboard_server_reuses_existing_compatible_instance tests/test_dashboard_server.py::DashboardServerGitTests::test_fetch_compatible_desk_health_rejects_remote_payload_url tests/test_dashboard_server.py::DashboardServerGitTests::test_select_dashboard_server_auto_port_skips_incompatible_occupied_port`
  passed: `3 passed`.
- `git diff --check` reported only pre-existing CRLF normalization warnings in
  unrelated WIP files.

Reviewer Gate:

- Prevents localhost health probing from becoming a browser redirect trust
  channel.

Residual Risk:

- This validates the health URL shape, not the identity of the local process
  beyond the existing `desk_health_v1` app marker.

Next:

- Commit this checkpoint, then run a wider backend checkpoint.

## Slice 11: Dashboard POST Request Boundary

Status: in progress.

Actions:

- Added a unified POST preflight that requires `application/json`.
- Added Origin/Referer checks: when present, POST mutation requests must come
  from an HTTP loopback URL on the same local port.
- Kept existing direct-handler unit tests compatible while exercising the real
  header boundary with focused tests.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_desk_action_run_endpoint_uses_requested_action_id tests/test_dashboard_server.py::DashboardServerGitTests::test_post_mutations_require_json_content_type_before_action tests/test_dashboard_server.py::DashboardServerGitTests::test_post_mutations_reject_non_loopback_origin_before_action tests/test_dashboard_server.py::DashboardServerGitTests::test_post_mutations_accept_json_from_loopback_same_port_origin tests/test_dashboard_server.py::DashboardServerGitTests::test_telegram_post_endpoints_require_loopback_client tests/test_dashboard_server.py::DashboardServerGitTests::test_local_state_mutation_endpoints_require_loopback_client`
  passed: `6 passed`.
- `git diff --check` reported only pre-existing CRLF normalization warnings in
  unrelated WIP files.

Reviewer Gate:

- Addresses the CSRF-style localhost mutation risk called out by the read-only
  audit: loopback client address alone is not enough when a browser can POST to
  `127.0.0.1`.

Residual Risk:

- Requests without Origin/Referer are allowed if they are JSON; this preserves
  non-browser local clients and direct tests. The browser threat path is covered
  by content-type plus origin/referer checks.

Next:

- Commit this checkpoint, run a wider backend checkpoint, then continue with
  the next bot/dashboard hardening slice.

## Slice 12: Profile Patch Workspace Scope

Status: completed.

Actions:

- Added a workspace resolver for Dashboard-sourced profile file paths.
- Applied it to DB-sourced profile patch suggestion, matching-preference patch,
  apply, and revert flows.
- Kept explicit low-level `profile_path` arguments available for tests and
  non-dashboard callers, while preventing polluted profile rows from driving
  Dashboard writes outside the project workspace.

Verification:

- `python -m pytest tests/test_monitor_state.py::MonitorStateTests::test_follow_up_patch_can_apply_to_profile_file tests/test_monitor_state.py::MonitorStateTests::test_dashboard_profile_patch_refuses_db_path_outside_project tests/test_monitor_state.py::MonitorStateTests::test_apply_profile_patch_refuses_when_profile_changed_after_suggestion tests/test_monitor_state.py::MonitorStateTests::test_applied_profile_patch_can_revert_to_snapshot_when_file_unchanged tests/test_monitor_state.py::MonitorStateTests::test_revert_profile_patch_refuses_when_profile_changed_after_apply`
  passed: `5 passed`.
- `git diff --check` reported only pre-existing CRLF normalization warnings in
  unrelated WIP files.

Reviewer Gate:

- Addresses the read-only audit concern that a polluted `profiles.path` could
  let Dashboard profile patch actions write outside the workspace.

Residual Risk:

- Explicit low-level function arguments can still target external paths. This is
  intentional for direct tests/non-dashboard usage; Dashboard routes do not pass
  those arguments.

Next:

- Commit this checkpoint, then continue with bot source-assistant external AI
  consent boundaries.

## Slice 13: Bot Source Assistant AI Consent Boundary

Status: completed.

Actions:

- Changed Telegram bot source-plan preview to call the Source Assistant in
  parser-only mode instead of setting `confirm_external_ai=true`.
- Added an inline maintenance note explaining that Telegram apply confirmation
  authorizes applying a cached local plan, not sending saved source metadata to
  an external model.
- Added Bot Gateway test coverage so the normal source-plan/apply flow proves
  the preview request keeps external AI disabled.

Verification:

- `python -m pytest tests/test_bot_gateway.py` passed: `29 passed`.

Reviewer Gate:

- Addresses the read-only audit concern that Bot source planning could bypass
  the Signal Desk external-AI confirmation boundary.

Residual Risk:

- Bot source planning remains local parser-only for existing-source operations
  that need semantic matching. Those cases should be handled by a future
  dedicated confirmation flow rather than silently falling back to external AI.

Next:

- Commit this checkpoint, then inspect the Bot free-text/knowledge-answer LLM
  defaults and decide whether another behavior hardening slice is warranted.
