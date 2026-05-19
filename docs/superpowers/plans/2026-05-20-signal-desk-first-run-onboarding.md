# Signal Desk First-Run Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel implementation, or `superpowers:executing-plans` for a single-worker pass. Use `superpowers:test-driven-development` for each behavior change and `superpowers:verification-before-completion` before claiming completion.

**Goal:** Make the Mac/source-checkout first run feel app-first: one current action, no CLI detour for normal users, and Settings exposes the lowest-friction path for the user's current setup stage.

**Architecture:** Keep the existing CLI, JSON contracts, and agent affordances intact, but route human first-run copy and Dashboard defaults through one onboarding funnel: demo -> goal/profile -> Telegram -> sources -> first review. Avoid a new onboarding state machine unless existing `dashboard_setup_status`, `buildJourneySteps`, `SourceImportPanel`, and desk action result surfaces cannot express the behavior.

**Tech Stack:** Python 3.12+/pytest/unittest, React 19 + TypeScript + Vitest, Vite Dashboard, POSIX shell setup/launcher scripts, local-first SQLite/state files.

## Product Judgment

The current Dashboard is directionally right, but the first-run experience breaks its own app-first promise. A normal Mac user should not finish setup and immediately be told to edit TOML, run quickstart commands, run a doctor command, log in via CLI, and launch monitor jobs manually.

Treat this as a product repair pass, not a visual redesign. The main product contract should be:

- The terminal gets the user into Signal Desk.
- Signal Desk gives one primary next action.
- Demo builds trust before credentials.
- Local/manual profile creation is not blocked by a missing AI key.
- Telegram, sources, and the first real review come before automation and alerts.
- Advanced CLI paths remain available, but they are not the default first-run narrative.

## Current Evidence

- `README.zh-CN.md` positions the product as app-first for normal users.
- `setup.sh` and `scripts/tgcs_setup.py` still end with CLI-era instructions.
- `dashboard/src/components/actions/journey-model.ts` currently mixes profile, privacy, demo, AI, Telegram, local files, first run, automation, and feedback under the setup flow.
- `dashboard/src/components/settings/source-import-panel.tsx` shows high-friction AI/profile-dependent controls before low-friction public/starter source paths when no profile exists.
- `scripts/desk_actions.py` has a `demo_render` action, but the success copy is generic and does not make the openable result feel like a completed product moment.
- `scripts/dashboard_server.py` and setup defaults still expose some `jobs-fast` assumptions, while docs say `market-news` is the normal starter and developer jobs are optional.

## Target First-Run Journey

1. User runs `./setup.sh` or opens the Mac launcher.
2. Terminal says setup is ready and points to Signal Desk, with one normal next step.
3. Dashboard Start first screen has one primary CTA: generate a demo report.
4. After the demo succeeds, the result remains openable and the next CTA becomes create/select a goal/profile.
5. Profile creation can proceed locally without an AI key.
6. User connects Telegram.
7. User adds sources through starter recommendations, known public sources, or Telegram folder discovery depending on readiness.
8. User runs the first real review.
9. Only after the first real review does the product surface automation, alerts, scheduled runs, and feedback loops.

## Non-Goals

- Do not redesign the whole Dashboard.
- Do not remove expert CLI commands.
- Do not introduce a second setup state machine if the existing projection and journey model can handle the change.
- Do not make Settings a tutorial page.
- Do not place automation, notifications, or scheduled delivery before the user's first real review.
- Do not make `jobs-fast` the visible default unless the user explicitly chose the developer-opportunity starter.
- Do not change security or privacy semantics.

## File Map

- `setup.sh`
  - Replace CLI-heavy completion text with one app-first next step.
  - Keep diagnostics for failed setup, but avoid sending normal users into manual TOML edits.

- `scripts/tgcs_setup.py`
  - Update `_print_init_next_steps` so `tgcs init` no longer reads like the only path is CLI operation.
  - Keep expert commands discoverable through help/docs, not as the default Mac completion path.
  - Preserve starter behavior and generated config contracts.

- `scripts/dashboard_setup.py`
  - Align setup stage/checklist copy with the product funnel.
  - Missing AI key must not imply that local profile creation, Telegram setup, or demo usage are blocked.

- `scripts/desk_actions.py`
  - Add product-specific success copy for `demo_render`.
  - Ensure result detail, artifact path, and next action make the demo feel complete and openable.

- `dashboard/src/components/actions/journey-model.ts`
  - Tighten the Start journey into one current setup action plus completed/pending context.
  - Move automation/feedback after first review readiness.
  - Rename vague setup language such as "Set up real sources" to user-language tied to the next action.

- `dashboard/src/components/actions.tsx`
  - Make the primary Start CTA follow the journey model.
  - Keep result links visible after successful demo and scans.

- `dashboard/src/components/settings/source-import-panel.tsx`
  - Reorder first-run Sources UI so low-friction paths appear first when no profile exists.
  - Hide or down-rank AI folder discovery until a profile exists.
  - Remove confusing `default` topic fallback from first-run starter behavior, or make the starter topic explicit.

- `dashboard/src/components/settings.tsx`
  - Only touch if `SourceImportPanel` needs profile/readiness data that is not already passed in.

- `dashboard/src/components/actions.test.tsx`
  - Contract tests for the Start funnel and demo result continuity.

- `dashboard/src/components/settings.test.tsx`
  - Contract tests for first-run Sources ordering and no-profile behavior.

- `tests/test_posix_launchers.py`
  - Contract tests for Mac/source-checkout setup copy.

- `tests/tgcs_cli/test_run_demo_init.py`
  - Contract tests for init/demo output and default starter behavior if needed.

- `tests/dashboard/test_desk_actions.py`
  - Contract tests for `demo_render` result copy and artifact behavior if not already covered elsewhere.

- `tests/monitor_state/test_projection.py`
  - Contract tests for setup status/checklist ordering and AI-key-not-blocking-local-setup semantics.

- `README.zh-CN.md`
  - Keep the public promise aligned with the actual first-run flow.

- `docs/desktop-platforms.md`
  - Update Mac/source-checkout instructions after implementation.

## Phase 0 - Guardrails And Baseline

- [ ] Run `git status --short` and note existing user changes. Do not revert unrelated files.
- [ ] Confirm the exact current setup copy and Dashboard behavior from the source files listed above.
- [ ] Run the current focused tests once if the working tree is stable:

```powershell
python -m pytest tests/test_posix_launchers.py tests/tgcs_cli/test_run_demo_init.py tests/dashboard/test_desk_actions.py tests/monitor_state/test_projection.py -q
```

```powershell
Push-Location dashboard
npm test -- dashboard/src/components/actions.test.tsx dashboard/src/components/settings.test.tsx
Pop-Location
```

- [ ] If baseline tests fail for unrelated reasons, record the failure and keep changes scoped to this plan.

## Phase 1 - Make Setup App-First

### 1.1 Add Setup Copy Contract Tests

- [ ] In `tests/test_posix_launchers.py`, add or update a setup smoke test that asserts the normal successful setup output has one human next step.
- [ ] The expected normal path should include Signal Desk language, such as `Signal Desk`, `./signal-desk`, or the local Dashboard URL.
- [ ] The normal path should not tell users to run this CLI sequence:

```text
tg-channel-scanner quickstart jobs
tg-channel-scanner doctor --fix
tg-channel-scanner telegram login
tg-channel-scanner monitor run
```

- [ ] Keep a small expert affordance acceptable, for example `Advanced CLI: tgcs --help`, but do not make it the main call to action.

### 1.2 Update `setup.sh`

- [ ] Replace post-install next steps with one app-first completion message.
- [ ] Suggested success shape:

```text
Signal Desk is ready.
Next: open Signal Desk with ./signal-desk, then use Start.
Advanced CLI users can run tgcs --help.
```

- [ ] Keep failure diagnostics and dependency instructions specific to the failure.
- [ ] Do not tell normal users to edit config files unless setup actually failed or the command was explicitly run in a headless/CLI-only mode.

### 1.3 Update `scripts/tgcs_setup.py`

- [ ] Update `_print_init_next_steps` to match app-first product language.
- [ ] Keep config paths and generated file summaries concise.
- [ ] Preserve CLI starter behavior, but change the default "what next" from a command chain to "open Start in Signal Desk".
- [ ] If CLI-specific next steps are still needed, put them under a short expert line, not the main path.

### 1.4 Acceptance

- [ ] A fresh setup does not leave a normal Mac user with four CLI chores.
- [ ] The completion copy names the app surface and one next action.
- [ ] CLI power users still have a discoverable path.

## Phase 2 - Align Setup Status With The Product Funnel

### 2.1 Add Projection Tests

- [ ] In `tests/monitor_state/test_projection.py` or the closest existing setup-status test, add cases for:
  - No AI key, no profile, no Telegram, no sources.
  - Demo-ready but no profile.
  - Profile exists, Telegram missing.
  - Profile and Telegram exist, sources missing.
  - First real run exists.

- [ ] Assert that missing AI key does not block local profile creation or Telegram setup wording.
- [ ] Assert the status/checklist order supports:

```text
demo -> profile/goal -> Telegram -> sources -> first review -> automation/delivery
```

### 2.2 Update `scripts/dashboard_setup.py`

- [ ] Keep `schema_version` stable unless contract changes truly require a version bump.
- [ ] Prefer copy/checklist changes over new stages.
- [ ] If a new stage is necessary, make it product-level and stable, not UI-internal.
- [ ] Suggested stage semantics:
  - `needs_demo` only if the UI relies on setup status for demo-first gating.
  - `needs_profile` for goal/profile work.
  - `needs_telegram` for Telegram setup.
  - `needs_sources` for starter/public/import work.
  - `needs_first_review` for first real scan.
  - `ready` after the first review path is complete enough.

- [ ] If the current stage model can already express this through checks, do not add new stages.

### 2.3 Acceptance

- [ ] Setup status no longer tells users that an AI key is the prerequisite for creating a useful local profile.
- [ ] The projection supports the Start journey without special-case UI hacks.

## Phase 3 - Tighten The Start Journey

### 3.1 Add/Update Journey Tests

- [ ] In `dashboard/src/components/actions.test.tsx`, add or strengthen tests for:
  - First-run Start shows the demo as the only primary action.
  - After demo success, the demo result remains openable.
  - After demo success and no profile, primary action is profile/goal creation, not another demo refresh.
  - Missing AI key does not hide local/manual profile setup.
  - Telegram appears before local source files once profile exists.
  - Automation/feedback does not appear before the first real review.

- [ ] Keep the tests about user-visible copy, primary buttons, and action availability rather than implementation details.

### 3.2 Update `dashboard/src/components/actions/journey-model.ts`

- [ ] Make the model choose one primary current step.
- [ ] Keep completed steps visible as confirmation, but visually secondary.
- [ ] Move automation and feedback behind first-review readiness.
- [ ] Rename setup labels from implementation terms to user terms.
- [ ] Suggested user-language labels:

```text
Generate demo report
Create your goal
Connect Telegram
Add sources
Run first review
Turn on automation
```

- [ ] Avoid "export", "config", "registry", "job", or "scheduler" language in the first-run path unless the user has entered an expert surface.

### 3.3 Update `dashboard/src/components/actions.tsx`

- [ ] Ensure the primary CTA reflects the model's current step.
- [ ] Keep `demo_render` success result visible and openable in the journey.
- [ ] If multiple actions are technically available, show only one as primary and move the rest to secondary/advanced treatment.

### 3.4 Acceptance

- [ ] On a clean local state, the Start view has one obvious next action.
- [ ] After demo success, the user sees both proof of value and the next real setup step.
- [ ] A user is not asked to understand automation before they have run a real review.

## Phase 4 - Make Demo Completion Feel Real

### 4.1 Add Desk Action Result Tests

- [ ] In `tests/dashboard/test_desk_actions.py`, add a test for `_desk_action_success_copy("demo_render", fallback)` or the public action result path.
- [ ] Assert the result copy says the demo report is ready/openable, not merely that an action named "Render offline demo" ran.
- [ ] If artifact behavior is already covered in frontend tests, keep backend assertions minimal.

### 4.2 Update `scripts/desk_actions.py`

- [ ] Add a `demo_render` branch to `_desk_action_success_copy`.
- [ ] Suggested copy:

```text
Demo report ready. Open it to see the kind of review Signal Desk will produce with your own sources.
```

- [ ] Ensure the result payload still includes artifact path/URL data expected by the frontend.
- [ ] Preserve JSON schema and existing action IDs.

### 4.3 Acceptance

- [ ] Demo success is understandable as a product outcome.
- [ ] The user can open the result without hunting through logs or files.

## Phase 5 - Rework Settings Sources For No-Profile First Run

### 5.1 Add Source Panel Tests

- [ ] In `dashboard/src/components/settings.test.tsx`, add or update `SourceImportPanel` tests for no-profile state.
- [ ] Assert that starter recommendations and known public sources are visible before AI folder discovery when no profile exists.
- [ ] Assert that AI folder discovery is disabled, collapsed, or moved below the low-friction source paths when no profile exists.
- [ ] Assert the UI does not imply sources are being filtered against `default`.
- [ ] Assert profile-dependent AI copy references a selected profile only when one exists.

### 5.2 Update `dashboard/src/components/settings/source-import-panel.tsx`

- [ ] Split the panel into readiness sections:
  - No profile: starter recommendations, known public sources, and create/select profile prompt.
  - Profile exists: AI discovery and profile-filtered Telegram folder paths.
  - Sources exist: refresh/review guidance remains behind a closed disclosure.

- [ ] Remove or replace this confusing fallback:

```ts
selectedProfile?.source_topics?.[0] || selectedProfileId || "default"
```

- [ ] Prefer an explicit starter topic for starter recommendations, or omit topic framing until the user has a profile.
- [ ] Keep Telegram folder discovery available, but do not make it the first thing a no-profile user has to parse.

### 5.3 Update `dashboard/src/components/settings.tsx` Only If Needed

- [ ] If `SourceImportPanel` already receives enough profile/readiness data, do not change `settings.tsx`.
- [ ] If it needs one extra prop, add the smallest stable prop and cover it in tests.

### 5.4 Acceptance

- [ ] A no-profile user can add starter/public sources without understanding AI profile filtering.
- [ ] A profile user can still use AI discovery.
- [ ] Existing source refresh guidance remains available but not distracting.

## Phase 6 - Clean Up Default Starter Semantics

### 6.1 Audit Defaults

- [ ] Review these files together:
  - `README.zh-CN.md`
  - `scripts/tgcs_setup.py`
  - `scripts/dashboard_server.py`
  - `scripts/desk_actions.py`
  - `tests/tgcs_cli/test_run_demo_init.py`

- [ ] Decide the visible normal default:
  - Recommended: `market-news` for general users.
  - Keep `jobs-fast` only for explicit developer-opportunity starter paths.

### 6.2 Add/Update Tests

- [ ] If setup/init writes both profiles for compatibility, test that the visible first-run default still points to the general starter.
- [ ] If `monitor_jobs_dry_run` remains jobs-specific, ensure it is not the first-run default CTA for general users.

### 6.3 Acceptance

- [ ] Public docs, setup copy, Dashboard first-run copy, and starter behavior do not contradict each other.
- [ ] Jobs-specific language appears only after the user chose that path or in expert/dev fixtures.

## Phase 7 - Docs And Handoff

### 7.1 Update User Docs

- [ ] Update `README.zh-CN.md` so the Mac/source-checkout path says:
  - Run setup.
  - Open Signal Desk.
  - Use Start.
  - Advanced CLI is optional.

- [ ] Update `docs/desktop-platforms.md` with the same app-first path.
- [ ] Do not duplicate long setup instructions across many docs. Keep one authoritative path and link to it if needed.

### 7.2 Add Maintenance Notes Only Where Useful

- [ ] Add code comments only for non-obvious ordering decisions, such as why automation stays after first review or why no-profile Sources shows starter/public paths before AI discovery.
- [ ] Do not add explanatory UI text that turns the app into documentation.

### 7.3 Acceptance

- [ ] Docs match the shipped behavior.
- [ ] The next maintainer can understand why first-run ordering exists without reading this plan.

## Phase 8 - Verification

### 8.1 Focused Automated Tests

Run from repo root:

```powershell
python -m pytest tests/test_posix_launchers.py tests/tgcs_cli/test_run_demo_init.py tests/dashboard/test_desk_actions.py tests/monitor_state/test_projection.py -q
```

Run from repo root:

```powershell
Push-Location dashboard
npm test -- dashboard/src/components/actions.test.tsx dashboard/src/components/settings.test.tsx
npm run build
Pop-Location
```

### 8.2 Fresh Local Browser Smoke

- [ ] Use a temporary project root/config dir so existing local state does not mask first-run behavior.
- [ ] Build the Dashboard before starting the server:

```powershell
Push-Location dashboard
npm run build
Pop-Location
```

- [ ] Start the Dashboard server with temp state. Adjust the port if busy:

```powershell
$tmp = Join-Path $env:TEMP ("tgcs-first-run-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TGCS_PROJECT_ROOT = $tmp
$env:TG_SCANNER_CONFIG_DIR = Join-Path $tmp ".tgcs"
python scripts/dashboard_server.py --host 127.0.0.1 --port 8785 --static-dir dashboard/dist --db (Join-Path $tmp ".tgcs/tgcs.db")
```

- [ ] Open `http://127.0.0.1:8785`.
- [ ] Verify:
  - Start first screen shows one primary demo CTA.
  - Demo succeeds and has an openable result.
  - After demo, the next CTA is create/select goal/profile.
  - Missing AI key does not block local profile setup.
  - Settings > Sources with no profile shows starter/public paths before AI discovery.
  - Adding starter sources does not label the user's topic as `default`.
  - Automation/alerts are not primary before the first real review.

### 8.3 Final Regression Check

- [ ] Run full Dashboard build:

```powershell
Push-Location dashboard
npm run build
Pop-Location
```

- [ ] If time allows, run the broader Python test set touched by setup/projection:

```powershell
python -m pytest tests/test_posix_launchers.py tests/tgcs_cli/test_run_demo_init.py tests/dashboard tests/monitor_state -q
```

## Implementation Order

Use this order to reduce churn:

1. Tests for setup copy.
2. `setup.sh` and `scripts/tgcs_setup.py`.
3. Projection/status tests and `scripts/dashboard_setup.py`.
4. Start journey tests and Start components.
5. Demo result tests and `scripts/desk_actions.py`.
6. Sources panel tests and Sources UI.
7. Starter default cleanup.
8. Docs.
9. Browser smoke.

## Checkpoint Policy

- Do not create many tiny commits unless the user asks for commits.
- If commits are requested, batch by phase:
  - setup copy
  - Dashboard onboarding
  - docs and verification
- Always keep unrelated user changes out of the commit.

## Definition Of Done

- [ ] Normal Mac/source-checkout setup ends with one app-first next action.
- [ ] Start first-run shows one primary CTA.
- [ ] Demo success leaves an openable result and a clear next step.
- [ ] Local/manual profile setup is not framed as blocked by a missing AI key.
- [ ] Settings > Sources no-profile state prioritizes starter/public source paths.
- [ ] AI discovery remains available after profile readiness.
- [ ] Automation/alerts appear after the first real review path, not before.
- [ ] General starter and jobs starter language no longer conflict.
- [ ] Focused Python tests pass.
- [ ] Focused Dashboard tests pass.
- [ ] `dashboard` build passes.
- [ ] Fresh browser smoke passes against temp local state.
- [ ] README and desktop docs match the implemented path.

## Risks And Watchpoints

- Setup output may be consumed by tests or scripts that expect the old CLI next-step wording. Keep schema and command behavior stable; change human copy only.
- The Dashboard may currently derive first-run behavior from both setup projection and action results. Avoid duplicating rules across both if one source can own the decision.
- Reordering Settings controls can accidentally hide advanced source import paths. Keep them available, just not first for no-profile users.
- Jobs-specific defaults may be relied on by developer-opportunity tests. Preserve explicit jobs starter paths while changing the general first-run default.
- Browser smoke must use fresh state; existing local config can hide first-run problems.

## Suggested Next Prompt

Implement Phase 1 through Phase 5 of `docs/superpowers/plans/2026-05-20-signal-desk-first-run-onboarding.md`, keeping changes scoped and running the focused Python and Dashboard tests before reporting back.
