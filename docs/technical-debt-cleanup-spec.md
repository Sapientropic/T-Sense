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

Observed from the 2026-05-14 local workspace:

- Current branch: `sapientropic/tech-debt-cleanup-20260513`.
- The dirty checkpoint backlog from the documentation handoff has been split,
  verified, and committed through packaging, report, scan, monitor, Bot Gateway,
  dashboard server tests, and dashboard settings UI slices.
- The worktree was clean after the implementation checkpoint commits. Future
  cleanup should start from a fresh focused slice instead of treating the old
  dirty handoff as still active.
- Each implementation checkpoint used focused mixed-tree verification first and
  staged snapshot verification before commit. Docker packaging smoke remains
  unverified because the local Docker client could not reach a daemon.
- CI still covers Python 3.12/3.13 on Linux, Windows, macOS; ruff; pytest;
  dashboard tests/build; shell syntax; POSIX launcher LF line endings.

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
- Bot Gateway status fixture coverage was later isolated as a checkpoint, but
  live Telegram API, live scheduler, keyring, and LLM knowledge-answer behavior
  remain operator checks.

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

## Current Debt Snapshot: 2026-05-14

The debt register below remains the long-form reasoning. This table is the
current triage view for what is still real after the later splits:

| Debt | Current Status | Next Useful Slice |
| --- | --- | --- |
| D1. WIP and branch hygiene | Cleared for the known backlog. The dirty implementation slices from the handoff are now checkpoint commits. | Keep using staged snapshot or clean worktree gates for future slices; do not use mixed-worktree gates as commit proof. |
| D2. Contract sprawl | Materially improved. Shared fixtures now cover the high-risk Python/TypeScript contracts, but `docs/agent-cli-contract.md` is still long. | Keep the contract doc as an index and move new guarantees into fixtures first, prose second. |
| D3. `dashboard_server.py` boundaries | Still high risk at `4320` lines, but Markdown/artifact rendering and dashboard tests are now separated. | Extract one route/action boundary at a time behind `tests/dashboard` focused gates. |
| D4. `monitor_state.py` boundaries | Still high risk at `2773` lines. Source insights moved out, and monitor-state tests are now focused under `tests/monitor_state`. | Continue splitting DB, projection, review-card, and feedback behavior behind existing focused tests. |
| D5. `report.py` coupling | Mostly reduced. `report.py` is now `503` lines; report behavior moved into `report_*` modules. | Treat `report_extraction.py`, `report_html.py`, and `report_sources.py` as the next review units rather than reopening the old monolith. |
| D6. Dashboard root/settings state | Settings/hooks checkpoint is committed. `main.tsx` is `546` lines and `settings.tsx` is `308`, but `profiles.tsx`, `actions.tsx`, `inbox.tsx`, and `runs.tsx` remain large. | Split `actions.tsx` or `profiles.tsx` only with focused component tests and dashboard build coverage. |
| D7. Runtime sanitizers | Still active. `sanitize/dashboard.ts`, `sanitize/desk.ts`, and `sanitize.test.ts` remain large. | Extract shared primitives only where fixture tests already prove the repeated behavior. |
| D8. Test concentration | Improved. Report, dashboard server, and monitor-state tests now live in focused directories, but several test files remain large. | Keep focused directories; next split targets are `tests/test_monitor.py`, `sanitize.test.ts`, and `tests/test_tgcs_cli.py`. |
| D9. Packaging metadata | Mostly complete for local Python packaging. Build, staged wheel install, `pipx`, and `uvx` smokes passed. | Re-run Docker smoke once a daemon is available; keep `signal-desk` as a source-checkout launcher until resources are package-safe. |
| D10. Documentation ownership | Current docs are aligned: this file is the debt authority, `docs/testing.md` is command authority, and quality logs are historical evidence. | Update this table and `docs/quality/task-state.md` whenever a new cleanup slice changes current status. |

Large current files are still the main maintainability signal:

| Area | File | Lines | Why It Matters |
| --- | ---: | ---: | --- |
| Python server | `scripts/dashboard_server.py` | 4320 | HTTP routing, local actions, credentials, sources, scheduler, artifacts, git, and bot gateway state are still coupled. |
| Python state | `scripts/monitor_state.py` | 2773 | SQLite schema, migrations, projections, review cards, alerts, feedback, profile patches, source stats, and setup status share one file. |
| Dashboard actions | `dashboard/src/components/actions.tsx` | 1119 | Start actions, progress, confirmations, and display mapping are concentrated. |
| Dashboard sanitize | `dashboard/src/domain/sanitize/dashboard.ts` | 1109 | Large runtime boundary with overlap against `sanitize/desk.ts`. |
| Dashboard profiles | `dashboard/src/components/profiles.tsx` | 1183 | Profile display, editing, draft patch state, and form controls are concentrated. |
| Dashboard inbox | `dashboard/src/components/inbox.tsx` | 813 | Review buckets, setup checks, filters, source health, and review actions are concentrated. |
| Python monitor runner | `scripts/monitor_runner.py` | 879 | Repeated-run orchestration and manifest behavior are now a focused but still sizeable boundary. |
| Report rendering | `scripts/report_html.py` | 610 | HTML rendering is separated from extraction but remains large enough to merit focused tests before visual/report changes. |

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

- Current branch is `sapientropic/tech-debt-cleanup-20260513`.
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
  - `scripts/desk_scheduler.py`: fixed dry-run scheduler and bot gateway
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
- Keep `docs/internal/specs/INDEX.md` as the private index authority for active
  specs. Public docs may link to stable summaries, but must not mirror internal
  implementation details.
- Keep temporary quality logs labeled as historical evidence or move them out of
  tracked docs once they are no longer needed for handoff.

Done when:

- New agents can find the right source in under one minute.
- No full contract is duplicated in multiple docs.
- Draft specs have a clear status and owner.

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

## Open Decisions For Owner

1. [⚠️ 需确认] Should the cleanup target v0.5 release hardening first, or
   developer velocity for post-v0.5 work? Recommendation: v0.5 hardening first,
   because the remaining risks are still release-facing: sanitizer boundaries,
   dashboard server routes, and local packaging smoke.
2. [⚠️ 需确认] Should behavior-changing fixes be allowed during cleanup?
   Recommendation: only when a test exposes a real privacy, contract, or setup
   bug; otherwise keep refactor-only.
3. Implementation specs live under gitignored `docs/internal/specs/`; the
   private `INDEX.md` there is the authority for active spec ownership.
4. [⚠️ 需确认] What is the acceptable local Python test runtime after cleanup?
   Current observed runtime is about 95 seconds. Recommendation: keep full suite
   under two minutes, but create smaller focused gates under ten seconds.
5. [⚠️ 需确认] Which remaining packaging target matters first: Docker or
   desktop launcher polish? Recommendation: Docker next for release
   reproducibility, because local build, staged wheel install, `pipx`, and
   `uvx` already passed in the checkpoint run.
6. [⚠️ 需确认] When can old compatibility paths be removed? Recommendation:
   keep them until at least one release after a documented migration path.
