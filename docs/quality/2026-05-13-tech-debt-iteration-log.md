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

Status: completed.

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

Status: completed.

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

Status: completed.

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

Status: completed.

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

Status: completed.

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

## Slice 14: Bot Free-Text And Knowledge LLM Opt-In

Status: completed.

Actions:

- Changed Bot Gateway defaults so free-text LLM routing is local-only unless
  the operator explicitly passes `--llm`.
- Kept `--no-llm` accepted as a compatibility/default marker and added `--llm`
  passthrough to the `tgcs bot run` facade.
- Added tests proving the default path does not call the intent-routing LLM,
  while explicit `--llm` opt-in remains available. The current modular Bot WIP
  also keeps knowledge-answer fallback local-only by tagging deterministic
  knowledge intents as `deterministic-no-llm`.

Verification:

- `python -m pytest tests/test_bot_gateway.py` passed: `32 passed`.
- `python -m pytest tests/test_tgcs_cli.py tests/test_bot_gateway.py` passed:
  `62 passed`.
- Applied the staged patch to a temporary `HEAD` export and re-ran
  `python -m pytest tests/test_tgcs_cli.py tests/test_bot_gateway.py` there:
  `62 passed`.

Reviewer Gate:

- Addresses the read-only audit concern that ordinary Bot free text and
  knowledge questions could default to external model calls.

Residual Risk:

- Explicit `--llm` still sends Telegram message text and selected local
  documentation snippets to the configured provider. That is now an operator
  opt-in, not the default.

Next:

- Commit this checkpoint, then continue with the next dashboard/API hardening
  candidate rather than expanding the Bot feature surface.

## Slice 15: Profile Draft-Note Fixture Alignment

Status: completed.

Root Cause:

- The backend full suite exposed one failure in
  `test_profile_draft_note_http_endpoint_creates_reviewable_patch`.
- The failing test registered a profile file under a temporary directory while
  Slice 12 correctly changed Dashboard-sourced profile writes to require paths
  inside `monitor_state.PROJECT_ROOT`.
- The production rejection was correct; the positive HTTP test fixture was
  still modeling the pre-hardening contract.

Actions:

- Scoped the positive draft-note HTTP test with
  `patch.object(monitor_state, "PROJECT_ROOT", root)` so the temporary profile
  is inside the test workspace.
- Kept the negative outside-workspace test intact.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_profile_draft_note_http_endpoint_creates_reviewable_patch tests/test_monitor_state.py::MonitorStateTests::test_dashboard_profile_patch_refuses_db_path_outside_project`
  passed: `2 passed`.
- `python -m pytest -q` passed:
  `447 passed, 2 skipped, 112 subtests passed`.

Reviewer Gate:

- This is a deterministic fixture correction after a full-suite failure; no
  production behavior was loosened.

Residual Risk:

- Existing direct-handler tests rely on lightweight fake handlers. The POST
  integrity tests still cover real header preflight separately.

Next:

- Commit this checkpoint, then continue with a dashboard/API contract hardening
  slice.

## Slice 16: Source API Schema Gates

Status: completed.

Actions:

- Added explicit frontend schema gates for Source Library responses
  (`desk_sources_v1`) before sanitizer fallback can run.
- Added explicit frontend schema gates for source import/source assistant
  responses (`desk_source_import_result_v1`) before sanitizer fallback can run.
- Reused small reader helpers so all source mutations share the same contract
  check rather than repeating loose sanitizer calls.
- Added API client tests proving schema-less but otherwise plausible source
  payloads now throw visible contract errors.

Verification:

- `npm test -- client` passed: `1` file, `7` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Extends the earlier API contract-drift fix beyond dashboard state and Desk
  actions into the source-management surface.

Residual Risk:

- Other endpoint families still rely on nested sanitizer null checks. This
  slice intentionally focused on source management because it is the highest
  privacy/behavior surface after the Bot AI boundary fixes.

Next:

- Commit this checkpoint, then run broader frontend verification and continue
  with the next highest-value contract or sanitizer hardening target.

## Slice 17: Delivery Target Schema Gate

Status: completed.

Actions:

- Made `DeliveryTarget` require `delivery_target_v1` on the frontend type.
- Changed the dashboard state sanitizer to drop schema-less delivery targets
  before rendering notification target configuration.
- Added client coverage proving a schema-less notification target mutation
  response throws instead of being accepted through sanitizer fallback.
- Updated display/projection/action test fixtures to use the current
  `delivery_target_v1` contract.

Verification:

- `npm test -- sanitize client display projections actions` passed: `5` files,
  `64` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Extends API contract hardening to a notification/chat-id related surface,
  where schema drift could otherwise quietly affect local delivery controls.

Residual Risk:

- Historical dashboard state payloads without `delivery_target_v1` will no
  longer render delivery targets. This matches the current backend contract and
  is preferable to rendering ambiguous notification configuration.

Next:

- Commit this checkpoint, then run full frontend verification again.

## Slice 18: AI Settings Schema Gate

Status: completed.

Actions:

- Made `DeskAiSettingsStatus` require `desk_ai_settings_status_v1`.
- Tightened the AI settings sanitizer so `{}` or schema-only payloads no longer
  become a plausible "no providers configured" state.
- Required core AI settings fields before rendering: non-negative integer
  `configured_count`, boolean `local_store_supported`, string `platform`,
  string `detail`, and a provider list.
- Added API client and sanitizer tests for empty, schema-only, and invalid-count
  AI settings payloads.

Verification:

- `npm test -- sanitize client settings` passed: `4` files, `49` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses Bernoulli's highest-risk finding: AI settings was the clearest case
  where contract drift could be misread as a valid unconfigured state.

Residual Risk:

- Provider entries are still sanitized by required provider fields and dropped
  individually when malformed. That keeps one bad provider from blanking the
  entire settings panel.

Next:

- Commit this checkpoint, then continue with action/result contract gates:
  `runDeskAction`, delivery test, and chat detection.

## Slice 19: Desk Action Result Schema Gate

Status: completed.

Actions:

- Required `desk_action_result_v1` before the frontend accepts Desk action
  result payloads.
- Changed `runDeskAction(actionId)` to reject responses whose nested
  `action_id` does not match the requested action.
- Added client tests for schema-less action results and mismatched action IDs.
- Updated sanitizer fixtures so positive cases use the current result schema
  while malformed artifact-path cases still prove path stripping.

Verification:

- `npm test -- sanitize client actions` passed: `3` files, `55` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Addresses Bernoulli's action/result finding for the highest-impact action
  execution path.

Residual Risk:

- Delivery test and chat detection result endpoints still need equivalent
  schema and target-id checks.

Next:

- Commit this checkpoint, then continue with delivery test/chat-detection gates.

## Slice 20: Delivery Result Schema Gates

Status: completed.

Actions:

- Required `desk_delivery_test_result_v1` for notification dry-run test results.
- Required `desk_delivery_chat_detection_v1` for chat-id detection results.
- Changed delivery test and chat detection client functions to reject nested
  results whose `target_id` does not match the requested target.
- Synchronized the legacy dashboard sanitizer entrypoint for delivery test
  results with the canonical Desk sanitizer.
- Added sanitizer/client tests for schema-less and wrong-target delivery result
  payloads.

Verification:

- `npm test -- sanitize client settings` passed: `4` files, `55` tests.
- `npm run typecheck` passed.

Reviewer Gate:

- Completes Bernoulli's delivery result gate finding for notification
  test/detect flows.

Residual Risk:

- Git, feedback, profile creation, scheduler, Telegram, and notification token
  result families still have softer schema gates and remain candidates for
  later slices.

Next:

- Commit this checkpoint, then continue with remaining mutation result gates.

## Slice 21: Git, Feedback, and Profile Mutation Result Gates

Status: completed.

Actions:

- Required `git_update_status_v1` before accepting Git check/pull responses.
- Required `feedback_export_result_v1`,
  `feedback_profile_suggestions_result_v1`, and `feedback_clear_result_v1`
  before accepting feedback mutation results.
- Added a typed `FeedbackClearResult` sanitizer with non-negative integer
  validation for `cleared_count`.
- Required `desk_profile_create_result_v1` before accepting profile creation
  results and made the frontend type reflect that required schema.
- Added client and sanitizer regressions for schema-less, wrong-schema, and
  plausible-but-invalid mutation payloads.

Verification:

- `npm test -- client sanitize` passed: `2` files, `46` tests.
- `npm run typecheck` passed.
- `npm test` passed: `13` files, `124` tests.
- Exported the staged index to a temporary tree to verify this checkpoint
  without unrelated working-tree WIP: `npm test -- client sanitize` passed
  (`2` files, `44` tests), `npm run typecheck` passed, and `npm test` passed
  (`13` files, `119` tests).

Reviewer Gate:

- Addresses Bernoulli's remaining schema-less mutation findings for Git,
  feedback export/profile suggestions/clear, and profile creation.

Residual Risk:

- Scheduler, Telegram, notification token, and some long-lived status payloads
  still rely on softer sanitizer gates. Those are lower mutation risk but remain
  the next hardening candidates.

Next:

- Commit this checkpoint, then continue with status-surface gates:
  scheduler, Telegram, notification token, and Bot Gateway if its WIP surface
  is stable enough to isolate safely.

## Slice 22: Status Surface Schema Gates

Status: completed.

Actions:

- Required `desk_scheduler_status_v1` before rendering scheduler status.
- Required `desk_telegram_status_v1` before rendering Telegram login/session
  status or accepting Telegram credential/login mutation responses.
- Required `desk_notification_token_status_v1` before rendering or accepting
  notification token status.
- Tightened token status validation so schema-only or partially typed payloads
  cannot become a plausible local-secret state.
- Added client and sanitizer coverage for schema-less scheduler, token, and
  Telegram payloads.

Verification:

- `npm test -- client sanitize` passed: `2` files, `49` tests.
- `npm run typecheck` passed.
- `npm test` passed: `13` files, `127` tests.
- Exported the staged index to a temporary tree to verify this checkpoint
  without unrelated working-tree WIP: `npm test -- client sanitize` passed
  (`2` files, `47` tests), `npm run typecheck` passed, and `npm test` passed
  (`13` files, `122` tests).

Reviewer Gate:

- Completes the remaining status-surface items from Bernoulli's audit:
  scheduler, Telegram, and notification token no longer accept schema-less
  payloads through frontend sanitizer fallback.

Residual Risk:

- Bot Gateway WIP is present in the working tree but was intentionally kept out
  of this slice unless it can be isolated safely. Remaining hardening should
  shift back to contract fixture coverage, privacy negative tests, or backend
  endpoint split points.

Next:

- Commit this checkpoint after staged-snapshot verification, then choose the
  next broad value slice rather than continuing to micro-fix schema edges.

## Slice 23: Recursive Review-Item Privacy Fixture

Status: completed.

Actions:

- Changed backend review-card item projection to strip raw/private keys
  recursively inside nested objects and arrays, not only at the top level.
- Kept `monitor_item_projection_v1` as the stored item contract while removing
  nested `raw_text`, token/API key, command, argv, session/path, and header-like
  fields from derived review items.
- Hardened the dashboard decision-state explanation sanitizer so private keys
  inside `explanations` do not render.
- Expanded the shared privacy contract fixture with nested backend and frontend
  denial strings so Python state, dashboard state, and feedback export all share
  the same privacy regression.

Verification:

- `python -m pytest tests/test_contract_privacy_fixtures.py tests/test_monitor_state.py::MonitorStateTests::test_review_card_item_sanitizer_strips_raw_media_text_fields -q`
  passed: `2` tests, `20` subtests.
- `python -m pytest tests/test_monitor_state.py -q` passed: `69` tests,
  `6` subtests.
- `npm test -- contract-privacy-fixtures sanitize` passed: `2` files,
  `29` tests.
- `npm run typecheck` passed.
- `npm test` passed: `13` files, `127` tests.
- Exported the staged index to a temporary tree to verify this checkpoint
  without unrelated working-tree WIP: Python privacy tests passed (`2` tests,
  `20` subtests), staged `tests/test_monitor_state.py` passed (`66` tests,
  `6` subtests), frontend targeted tests passed (`2` files, `27` tests), and
  `npm run typecheck` passed.

Reviewer Gate:

- This directly advances the spec's privacy goal: raw Telegram text, secrets,
  local paths, command strings, and argv now stay out even when they arrive
  nested inside otherwise allowed review-item structures.

Residual Risk:

- Key-based recursive stripping cannot detect sensitive values hidden under
  benign keys. That would need a separate content classifier or stricter
  allowlist for item projections, which may be too lossy without product
  review.

Next:

- Commit this checkpoint after staged-snapshot verification, then triage the
  parallel privacy audit and continue with the next broad high-value item.

## Slice 24: Desk Action And Git Redaction Boundaries

Status: completed.

Actions:

- Applied the parallel privacy audit's highest-priority findings for Desk
  action fallback output and Git update status.
- Routed Desk action non-JSON stdout success fallback, failure stderr/stdout
  fallback, and JSON error message/next-step fields through the local redactor.
- Expanded that redactor to cover Telegram bot tokens, provider/API keys,
  bearer authorization headers, secret-like env assignments, argv dumps,
  chat-id fields, and local paths.
- Changed Git update status to redact fetch errors, return only scrubbed
  `repo_url`, omit raw `remote_url`, and require loopback access for
  `/api/git/check-updates`.

Verification:

- `python -m pytest tests/test_dashboard_server.py::DashboardServerGitTests::test_git_update_status_redacts_remote_and_fetch_error tests/test_dashboard_server.py::DashboardServerGitTests::test_run_desk_action_redacts_stdout_and_stderr_fallback_details tests/test_dashboard_server.py::DashboardServerGitTests::test_local_state_mutation_endpoints_require_loopback_client -q`
  passed: `3` tests, `12` subtests.
- `python -m pytest tests/test_dashboard_server.py -q` passed: `142` tests,
  `66` subtests.
- Exported the staged index to a temporary tree to verify this checkpoint
  without unrelated working-tree WIP: targeted dashboard tests passed (`3`
  tests, `12` subtests), and staged `tests/test_dashboard_server.py` passed
  (`131` tests, `66` subtests).

Reviewer Gate:

- Triage accepted Ptolemy's top two quick-landable findings:
  Desk action fallback output leakage and Git update leakage/loopback gap.

Residual Risk:

- Report artifacts intentionally still contain raw original text in local
  report HTML/Markdown; Ptolemy marked that as a product decision, not a safe
  unilateral change.
- Profile draft/profile preference text still needs a secret/path rejection or
  redaction pass before retained docs are considered hardened.

Next:

- Commit this checkpoint after staged-snapshot verification, then continue with
  profile draft/preference input redaction or bot reply redaction expansion.

## Slice 25: Profile Input Private-Fragment Rejection

Status: completed.

Actions:

- Added a shared profile-text private-fragment guard in `monitor_state` so
  direct profile patch creation rejects obvious bot tokens, provider/API keys,
  bearer authorization headers, secret env/key-value assignments, argv dumps,
  chat-id fields, and local paths before writing `profile_patch_suggestions`.
- Applied the same guard at dashboard route boundaries for profile draft notes
  and matching-preference edits before opening the local state database.
- Applied the guard to profile creation input after Markdown/text/PDF parsing
  and length checks, so new local profile Markdown is not created from obvious
  credential or path dumps.

Verification:

- `python -m pytest tests/test_monitor_state.py::MonitorStateTests::test_profile_patch_suggestions_reject_private_fragments tests/test_monitor_state.py::MonitorStateTests::test_profile_text_private_fragment_detector_covers_common_dumps tests/test_monitor_state.py::MonitorStateTests::test_profile_patch_rejects_existing_private_profile_text_before_storing_copy tests/test_monitor_state.py::MonitorStateTests::test_follow_up_private_note_rejects_before_feedback_write tests/test_monitor_state.py::MonitorStateTests::test_follow_up_patch_can_apply_to_profile_file tests/test_dashboard_server.py::DashboardServerGitTests::test_profile_draft_note_http_endpoint_rejects_invalid_payloads tests/test_dashboard_server.py::DashboardServerGitTests::test_profile_matching_preferences_http_endpoint_rejects_private_fragments tests/test_dashboard_server.py::DashboardServerGitTests::test_profile_create_endpoint_rejects_invalid_payloads -q`
  passed: `8` tests, `20` subtests.
- `python -m pytest tests/test_monitor_state.py tests/test_dashboard_server.py -q`
  passed: `216` tests, `86` subtests.
- Exported the staged index to a temporary tree to verify this checkpoint
  without unrelated working-tree WIP: targeted profile privacy tests passed
  (`8` tests, `20` subtests), and staged `tests/test_monitor_state.py` plus
  staged `tests/test_dashboard_server.py` passed (`202` tests, `86` subtests).

Reviewer Gate:

- Accepted Ptolemy's profile draft/profile preference privacy finding as the
  slice input.
- Lagrange returned no P0, accepted P1/P2 gaps: existing profile text could be
  copied into patch suggestions; common private-fragment patterns were missing;
  and `follow_up` notes were validated after feedback writes in direct calls.
- All three findings were accepted and fixed in this slice.

Residual Risk:

- This is deterministic pattern rejection for clearly private fragments; it
  does not classify arbitrary raw Telegram transcript pasted under benign
  wording.
- Report artifacts still intentionally keep original local report text pending
  a product decision.

Next:

- Commit this checkpoint, then continue with bot reply redaction expansion or
  the next remaining privacy/output boundary.

## Slice 26: Bot Reply Redaction Boundary

Status: completed.

Actions:

- Added a baseline Telegram reply redactor in `bot_gateway.py` for bot tokens,
  provider/API keys, GitHub/Slack-style access tokens, bearer headers, secret
  env/key-value assignments, argv/args dumps, Windows/UNC/POSIX private paths,
  chat-id fields, bare long chat IDs, raw message JSON fields, and traceback
  bodies.
- Routed `TelegramBotApi.send_message`, BotGateway's fake-API/test path, and
  summary helpers through the redactor so both production sends and direct
  helper outputs stay clean.
- Also strengthened the current working-tree bot action redactor used by the
  in-progress bot refactor, without staging that unrelated refactor.

Verification:

- Staged snapshot targeted bot tests passed:
  `python -m pytest .codex-index-check\tests\test_bot_gateway.py::BotGatewayTests::test_redaction_removes_sensitive_telegram_reply_content .codex-index-check\tests\test_bot_gateway.py::BotGatewayTests::test_gateway_send_message_redacts_with_fake_api .codex-index-check\tests\test_bot_gateway.py::BotGatewayTests::test_summary_helpers_redact_private_snapshot_fields -q`
  passed: `3` tests.
- Staged snapshot `python -m pytest .codex-index-check\tests\test_bot_gateway.py -q`
  passed: `16` tests.
- Mixed working-tree `python -m pytest tests/test_bot_gateway.py -q` passed:
  `32` tests.

Reviewer Gate:

- This directly addresses Ptolemy's remaining quick-landable bot reply
  redaction finding.
- No additional external reviewer was launched for this narrow deterministic
  slice; the test matrix covers the previously missing private-fragment forms.

Residual Risk:

- Redaction remains deterministic pattern matching; it cannot prove arbitrary
  free-form text is not private if it does not look like a known secret, path,
  argv dump, traceback, or chat identifier.

Next:

- Commit this checkpoint, then continue with the next v0.5 privacy/output or
  local-boundary hardening item.

## Slice 27: `semantic_items_v1` Private Field Rejection

Status: completed.

Actions:

- Hardened `semantic_items_v1` ingestion so agent-produced items recursively
  reject raw/private/control-plane fields such as `raw_text`, `message`,
  `content`, `transcript`, `argv`, `token`, `path`, `session`, `headers`, and
  secret-like suffixes before report generation.
- Kept normal semantic extraction fields and source-message refs unchanged.
- Added an integration regression through `report.main --items-json --format
  json` to prove rejected raw text is not echoed back through the agent error
  envelope.

Verification:

- `python -m pytest tests/test_agent_semantic_fallback.py::AgentSemanticFallbackTests::test_report_items_json_rejects_private_semantic_item_fields tests/test_agent_semantic_fallback.py::AgentSemanticFallbackTests::test_report_items_json_renders_without_llm_key tests/test_agent_semantic_fallback.py::AgentSemanticFallbackTests::test_report_items_json_rejects_unknown_source_refs -q`
  passed: `3` tests.
- `python -m pytest tests/test_agent_semantic_fallback.py tests/test_report.py -q`
  passed: `46` tests.
- Staged snapshot verification passed without unrelated WIP:
  targeted agent semantic tests passed (`3` tests), and staged
  `tests/test_agent_semantic_fallback.py` plus staged `tests/test_report.py`
  passed (`46` tests).

Reviewer Gate:

- This follows Phase 1 of the spec directly: agent JSON contracts must not
  become a backdoor raw Telegram or local control-plane store.
- External review was not available due subagent thread limit; deterministic
  negative tests cover the intended contract.

Residual Risk:

- Report HTML/Markdown can still intentionally render original message text
  from the scan input as a local artifact. This slice only constrains agent
  `semantic_items_v1` output, not the product report decision.

Next:

- Commit this checkpoint, then continue with shared contract fixture coverage
  or another privacy negative test from Phase 1.

## Slice 28: Delivery Attempt Error Redaction

Status: completed.

Actions:

- Added a delivery-error redactor at `DeliveryAttempt.to_dict()` so monitor
  result JSON, run manifests, dashboard state, and tests that consume delivery
  attempts do not receive raw bot tokens, provider keys, bearer headers,
  secret env/key-value assignments, argv/args dumps, local paths, UNC paths, or
  chat IDs through error strings.
- Kept dry-run/live status shape unchanged; only the optional `error` field is
  sanitized at the serialization boundary.

Verification:

- `python -m pytest tests/test_delivery.py -q` passed: `7` tests.
- First attempted monitor verification used a stale test name and ran no tests;
  corrected immediately.
- `python -m pytest tests/test_delivery.py tests/test_monitor.py -q` passed:
  `28` tests.
- Staged snapshot `python -m pytest .codex-index-check\tests\test_delivery.py .codex-index-check\tests\test_monitor.py -q`
  passed: `28` tests.

Reviewer Gate:

- This is a deterministic privacy/output boundary slice. External review was
  skipped because the blast radius is one serialization boundary plus focused
  regression tests.

Residual Risk:

- In-memory `DeliveryAttempt.error` remains the original adapter error for local
  debugging. The hardened guarantee is for serialized contract surfaces.

Next:

- Commit this checkpoint, then continue with shared contract fixture coverage
  or another Phase 1 privacy negative test.

## Slice 29: Shared Agent And Monitor Contract Fixtures

Status: completed.

Actions:

- Added fixture-backed coverage for `agent_envelope_v1` success/error helpers,
  valid and rejected `semantic_items_v1`, `monitor_run_result_v1`, and a
  normalized `run_manifest_v1` shape.
- Used a real `monitor.py run --scan-input --format json` path with a fake
  report subprocess to compare monitor output and manifest projections against
  golden fixtures without requiring Telegram or LLM credentials.
- Updated `docs/agent-cli-contract.md` to point future contract changes at
  `tests/fixtures/contracts/` and the matching Python/TypeScript fixture tests.

Verification:

- `python -m pytest tests/test_contract_fixtures.py -q` passed: `4` tests and
  `2` subtests.
- `python -m ruff check tests/test_contract_fixtures.py` passed.
- `python -m pytest tests/test_contract_fixtures.py tests/test_report_contracts.py tests/test_agent_native_cli.py tests/test_agent_semantic_fallback.py tests/test_monitor.py -q`
  passed: `37` tests and `22` subtests.
- `git diff --check -- tests/test_contract_fixtures.py tests/fixtures/contracts docs/agent-cli-contract.md docs/quality/task-state.md docs/quality/2026-05-13-tech-debt-iteration-log.md`
  passed.

Reviewer Gate:

- Independent explorer Rawls completed a read-only contract-gap review.
- Accepted finding: the highest-value immediate slice is
  `monitor_run_result_v1` plus `run_manifest_v1` fixtures because it avoids the
  dashboard dirty WIP while locking the recently hardened delivery/monitor
  serialization boundary.
- Already covered in this slice: agent envelope and semantic-items fixtures,
  matching Rawls' fourth suggested fixture group.
- Deferred: dashboard-state and Desk-action/source fixture groups remain
  valuable next slices, but dashboard domain/server files are currently dirty
  and should be touched deliberately.

Residual Risk:

- The `run_manifest_v1` fixture intentionally compares a normalized manifest
  shape rather than hashes, timestamps, and executed command argv because those
  fields are run-local evidence, not stable cross-environment contract text.

Next:

- Stage and commit this checkpoint, then continue with the next Phase 1
  fixture group or another privacy boundary.

## Slice 30: `dashboard_state_v1` Shared Projection Fixture

Status: in progress.

Actions:

- Added `dashboard_state_v1.projection.json` as a shared fixture for a
  representative Dashboard state projection covering profiles, runs, inbox,
  delivery target status, feedback summary, setup status, opportunity summary,
  source insights, and validation summary.
- Added a Python backend contract test that builds an in-memory
  `monitor_state.dashboard_snapshot()` from real state helpers, normalizes only
  stable fields, and compares it to the shared fixture.
- Added a new Vitest file that imports the same fixture and proves
  `sanitizeDashboardState()` strips raw Telegram text, local paths, bot tokens,
  argv, and unsafe source URLs without touching the existing dirty sanitizer
  test file.

Verification:

- `python -m pytest tests/test_dashboard_state_contracts.py -q` passed:
  `1` test and `5` subtests.
- `python -m ruff check tests/test_dashboard_state_contracts.py` passed.
- `cd dashboard; npm test -- --run dashboard-state-contract-fixtures` passed:
  `1` test file, `1` test.
- Mixed working tree broader gate passed:
  `python -m pytest tests/test_dashboard_state_contracts.py tests/test_contract_privacy_fixtures.py tests/test_monitor_state.py -q`
  passed `75` tests and `41` subtests.
- Mixed working tree frontend fixture gate passed:
  `cd dashboard; npm test -- --run dashboard-state-contract-fixtures contract-privacy-fixtures`
  passed `2` test files and `2` tests.
- Staged snapshot verification passed after checking out the index to a temp
  directory and reusing only `dashboard/node_modules`:
  Python passed `72` tests and `41` subtests; frontend fixture tests passed
  `2` test files and `2` tests.
- `git diff --check -- dashboard/src/domain/dashboard-state-contract-fixtures.test.ts tests/test_dashboard_state_contracts.py tests/fixtures/contracts/dashboard_state_v1.projection.json docs/quality/task-state.md docs/quality/2026-05-13-tech-debt-iteration-log.md`
  passed.

Reviewer Gate:

- This implements Rawls' second recommended fixture slice, with the risk
  mitigation they called out: lock stable fields and privacy denied strings
  rather than taking a full brittle UI snapshot.

Residual Risk:

- The backend fixture intentionally normalizes volatile ids/timestamps and does
  not claim complete Dashboard UI coverage. It locks the cross-boundary
  projection shape and privacy behavior.
- The fixture also normalizes fields currently affected by unrelated dirty WIP
  (`diagnostic_info_count` and `opportunity_status`) so the committed test does
  not depend on work outside this checkpoint.

Next:

- Stage and commit this checkpoint, then continue with Desk action/source
  fixture coverage or another Phase 1 boundary.

## Slice 31: Desk Boundary Fixture Coverage

Status: in progress.

Actions:

- Added `desk_boundary_v1.json` for selected `desk_actions_v1`,
  `desk_action_result_v1`, and `desk_sources_v1` payloads.
- Added backend tests that compare `dashboard_server.desk_actions()`,
  `_desk_action_result()`, and `desk_sources()` against the fixture while
  proving `argv`, `artifact_keys`, `timeout`, local absolute paths, and secret
  markers do not surface.
- Added a focused Vitest file that imports the same fixture and verifies
  `sanitizeDeskActions()`, `sanitizeDeskActionResult()`, and
  `sanitizeDeskSourcesResult()` drop backend-only or private fields.

Verification:

- `python -m pytest tests/test_desk_contract_fixtures.py -q` passed:
  `3` tests and `4` subtests.
- `python -m ruff check tests/test_desk_contract_fixtures.py` passed.
- `cd dashboard; npm test -- --run desk-contract-fixtures` passed:
  `1` test file and `1` test.
- Broader related backend gate passed:
  `python -m pytest tests/test_desk_contract_fixtures.py tests/test_dashboard_server.py -k "desk_actions or desk_source or desk_action_result" -q`
  passed `19` tests, `14` subtests, `127` deselected.
- Broader related frontend gate passed:
  `cd dashboard; npm test -- --run desk-contract-fixtures sanitize client`
  passed `3` test files and `50` tests.
- `git diff --check -- tests/fixtures/contracts/desk_boundary_v1.json tests/test_desk_contract_fixtures.py dashboard/src/domain/desk-contract-fixtures.test.ts`
  passed.
- Staged snapshot verification passed after checking out the index to a temp
  directory and reusing only `dashboard/node_modules`: backend passed `19`
  tests, `116` deselected, `14` subtests; frontend passed `3` test files and
  `48` tests.

Reviewer Gate:

- This implements Rawls' third fixture-group recommendation. The fixture locks
  action ids, run modes, display-command safety, action-result artifact path
  shape, and saved-source library shape without snapshotting every route.

Residual Risk:

- The Desk action fixture intentionally covers a representative subset of
  high-risk action modes rather than every action. Existing broader
  `test_dashboard_server.py` tests remain the wider route behavior net.

Next:

- Commit this checkpoint, then continue with the next high-value Phase 1
  boundary.

## Slice 32: Desk Source Access Health Summary Fixture

Status: in progress.

Actions:

- Added `desk_source_access_health_v1.summary.json` as a shared contract
  fixture for the aggregate source-access health summary exposed through Desk
  action results and setup checks.
- Added a backend test that builds a full internal source-access health payload
  with per-source private details and asserts `_source_access_action_summary()`
  emits only aggregate counts, reason counts, timestamps, and probe-window
  bounds.
- Added a frontend fixture test proving `sanitizeDeskActionResult()` keeps the
  nested `source_access` summary aggregate-only and drops per-source details,
  raw text, local paths, and token-like fields.

Verification:

- `python -m pytest tests/test_desk_source_access_contracts.py -q` passed:
  `1` test and `4` subtests.
- `python -m ruff check tests/test_desk_source_access_contracts.py` passed.
- `cd dashboard; npm test -- --run desk-source-access-contract-fixtures` passed:
  `1` test file and `1` test.
- Broader related backend gate passed:
  `python -m pytest tests/test_desk_source_access_contracts.py tests/test_dashboard_server.py -k "source_access or desk_source" -q`
  passed `18` tests, `14` subtests, `126` deselected.
- Broader related frontend gate passed:
  `cd dashboard; npm test -- --run desk-source-access-contract-fixtures desk-contract-fixtures sanitize`
  passed `3` test files and `30` tests.
- `git diff --check -- tests/fixtures/contracts/desk_source_access_health_v1.summary.json tests/test_desk_source_access_contracts.py dashboard/src/domain/desk-source-access-contract-fixtures.test.ts`
  passed.
- Staged snapshot verification passed after checking out the index to a temp
  directory and reusing only `dashboard/node_modules`: backend passed `18`
  tests, `115` deselected, `14` subtests; frontend passed `3` test files and
  `28` tests.

Reviewer Gate:

- This extends Rawls' Desk boundary recommendation to the cached source-access
  health contract, which is a high-risk local Telegram boundary because full
  probe records can contain source-specific failure detail.

Residual Risk:

- This does not exercise live Telegram access. It locks the serialization
  boundary from internal health payload to public Desk summary and frontend
  sanitizer behavior.

Next:

- Commit this checkpoint, then continue until the 14:00 stop condition.

## Slice 34: `agent_extraction_request_v1` Projection Helper Extraction

Status: in progress.

Actions:

- Moved `AGENT_EXTRACTION_REQUEST_SCHEMA_VERSION`, scan meta allowlisting,
  selected-message projection, and profile field contract projection into
  `scripts/report_contracts.py`.
- Kept `build_agent_extraction_request()` in `report.py` because it still
  coordinates prompt construction and request file paths.
- Preserved public names in `report.py` by importing the extracted helpers, so
  existing tests and callers that reach through `report` keep working.

Verification:

- `python -m ruff check scripts/report.py scripts/report_contracts.py` passed.
- `python -m pytest tests/test_contract_fixtures.py tests/test_report_contracts.py tests/test_agent_semantic_fallback.py tests/test_report.py -q`
  passed `51` tests and `22` subtests.
- Staged snapshot verification passed after checking out the index to a temp
  directory: ruff passed and the same report contract test set passed `51`
  tests and `22` subtests.

Reviewer Gate:

- This completes the spec's first `report_contracts.py` extraction target more
  fully without moving provider or rendering code.

Residual Risk:

- `build_agent_extraction_request()` still lives in `report.py`; moving it
  safely would require separating prompt construction from request shaping and
  is better handled as a later, separately verified slice.

Next:

- Commit this checkpoint, then continue until the 14:00 stop condition.

## Slice 33: `semantic_items_v1` Report Contract Extraction

Status: in progress.

Actions:

- Added `scripts/report_contracts.py` as a pure JSON contract module for
  `semantic_items_v1` schema version, private-field detection, source ref
  validation, and semantic item validation.
- Updated `scripts/report.py` to import `SEMANTIC_ITEMS_SCHEMA_VERSION` and
  `validate_semantic_items()` from the new module while leaving provider,
  prompt, Markdown, and HTML responsibilities unchanged.
- Kept existing report helper names such as `build_message_lookup()` in
  `report.py` to avoid widening the refactor beyond the contract boundary.

Verification:

- `python -m ruff check scripts/report.py scripts/report_contracts.py` passed.
- `python -m pytest tests/test_contract_fixtures.py tests/test_report_contracts.py tests/test_agent_semantic_fallback.py tests/test_report.py -q`
  passed `51` tests and `22` subtests.
- Staged snapshot verification passed after checking out the index to a temp
  directory: `python -m ruff check scripts/report.py scripts/report_contracts.py`
  passed, and the same report contract test set passed `51` tests and `22`
  subtests.

Reviewer Gate:

- This follows the spec's Phase 2 order for `report.py`: extract contract
  validation before provider or rendering code. The blast radius is limited to
  semantic item validation and schema constants.

Residual Risk:

- The new module intentionally duplicates a tiny source-ref normalization path
  instead of moving all report source-ref helpers at once. That keeps this
  checkpoint narrow; a later cleanup can consolidate helpers after more report
  contracts are moved.

Next:

- Commit this checkpoint, then continue until the 14:00 stop condition.
