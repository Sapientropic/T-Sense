state: remaining_tech_debt_deep_split_verified
mode: Standard
run_shape: parallel_boundary_cleanup
slice_goal: "Split the remaining dashboard_server, monitor_state, Dashboard Actions/Profiles, dashboard projection, Desk credentials/sources/actions, and sanitizer debt while preserving API/schema/facade compatibility."
stop_condition: "Focused backend, monitor-state, dashboard UI, sanitizer, and contract gates pass after the split."
handoff_policy: evidence_backed_summary
continuation_policy: "Use docs/technical-debt-cleanup-spec.md as the debt authority; continue with one remaining boundary at a time and keep old facade exports until downstream callers move."
intake_status: explicit_user_request
gate_status: full_gates_and_operator_checks_passed
blockers: []
needs_human: []
residual_risk: "Live checks passed on this workstation. Docker Desktop, Telegram session/API, Windows Task Scheduler, Windows Credential Manager, and the configured LLM provider are still environment-dependent release checks."
completed_slices:
  - "dashboard_server artifact helpers moved to scripts/desk_artifacts.py with dashboard_server re-export compatibility."
  - "dashboard_server git helpers moved to scripts/desk_git.py with dashboard_server wrapper compatibility."
  - "dashboard_server scheduler and Bot Gateway background helpers moved to scripts/desk_scheduler.py with monkeypatch compatibility preserved."
  - "monitor_state DB/schema helpers moved to scripts/monitor_db.py."
  - "monitor_state shared constants/privacy guards moved to scripts/monitor_common.py."
  - "monitor_state review-card CRUD/actions moved to scripts/review_cards.py."
  - "monitor_state alert candidate/suppression/event helpers moved to scripts/monitor_alerts.py."
  - "monitor_state feedback export/summary/validation helpers moved to scripts/monitor_feedback.py."
  - "monitor_state profile patch lifecycle moved to scripts/profile_patches.py."
  - "monitor_state dashboard snapshot/run/report/setup/opportunity projection moved to scripts/dashboard_projection.py."
  - "dashboard_server Telegram credentials/login, delivery target detection, notification token, AI key, and Desk action env helpers moved to scripts/desk_credentials.py."
  - "dashboard_server source import/list/update/remove, source access health/probe/repair, and source assistant helpers moved to scripts/desk_sources.py."
  - "dashboard_server Desk action catalog, active action state, result projection, safe output text, and run_desk_action moved to scripts/desk_actions.py."
  - "Dashboard actions.tsx reduced to composition; Actions subcomponents/model split under dashboard/src/components/actions/."
  - "Dashboard profiles.tsx reduced to composition; Profiles subcomponents/model split under dashboard/src/components/profiles/."
  - "Sanitizer shared primitives added to dashboard/src/domain/sanitize/shared.ts with sanitize-shared Vitest coverage."
  - "dashboard/src/domain/sanitize/dashboard.ts reduced to a public facade; dashboard state sanitizers split into dashboard-common, dashboard-state, dashboard-review, dashboard-runs, dashboard-profiles, dashboard-delivery, and dashboard-summary modules."
verification:
  - "python -m pytest tests/dashboard -q -> 149 passed, 71 subtests passed"
  - "python -m pytest tests/monitor_state -q -> 81 passed, 24 subtests passed"
  - "python -m pytest tests/test_desk_contract_fixtures.py tests/test_desk_source_access_contracts.py tests/test_desk_settings_contracts.py tests/test_dashboard_state_contracts.py tests/test_contract_privacy_fixtures.py -q -> 7 passed, 58 subtests passed"
  - "cd dashboard; npm test -- --run sanitize sanitize-dashboard sanitize-shared -> 3 files, 35 tests passed"
  - "cd dashboard; npm run build -> passed"
  - "python -m ruff check . -> passed"
  - "python -m pytest -q -> 489 passed, 2 skipped, 195 subtests passed"
  - "cd dashboard; npm test -- --run -> 21 files, 147 tests passed"
  - "git diff --check -> passed"
operator_checks:
  - "Docker Desktop 4.65.0 / engine 29.2.1 reachable after startup; docker build -t tgcs-local-smoke:<temp> . -> exit 0"
  - "Docker demo container -> exit 0, generated one demo report in a temporary mounted output directory; temporary directory and image removed."
  - "Docker doctor container with dummy Telegram env -> exit 0, summary pass=7 warn=5 fail=0; warnings were optional LLM dependency inside image, missing session, ffmpeg, dashboard assets, and no real LLM key."
  - "Live Telegram status -> credentials_ready=true, session_ready=true, login_state=authorized."
  - "Live source-access probe with TGCS_SOURCE_ACCESS_PROBE_MAX_SOURCES=3 -> checked=3 of 67, accessible=2, quiet=1, inaccessible=0, truncated=64."
  - "Live Windows Task Scheduler dry-run task with random name -> install exit 0, status installed, remove exit 0, final status not_installed."
  - "Live Windows Credential Manager smoke -> random secret write/read/delete passed; post-delete read returned empty."
  - "Live LLM structured call -> provider=deepseek, model=deepseek-v4-flash, JSON response status=TGCS_LIVE_LLM_OK, total_tokens=58."
next_action: "Commit as one compatibility-preserving refactor slice if no new edits land."
candidate_slices:
  - "Split dashboard inbox/runs components only with focused component tests and production build coverage."
  - "Split large legacy dashboard/src/domain/sanitize.test.ts by dashboard/desk/fixture areas; keep current sanitizer modules as the implementation authority."
  - "Consider profile creation/profile runtime helpers only when those server/state areas change next."
last_update: "2026-05-14T04:09:37+08:00"
checkpoint_ready: true
