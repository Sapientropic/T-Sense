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
