# Signal Desk Quality Iteration

Current truth for the 2026-05-11 quality loop. Product rules stay in `.frontend-design-context.md` and `docs/v0.5-alpha-alert-review-inbox.md`; this file only tracks this time-boxed review and repair run.

## Operating Contract

- Mode: Standard, with degraded reviewer gate because no external KIMI/GEMINI command is available in this session.
- Stop condition: keep opening useful, checkpointable slices until 2026-05-11 13:00 +08:00, then write the final handoff.
- Scope: Signal Desk dashboard across desktop/mobile, generated report touchpoints where linked from Desk, README/ROADMAP/doc truth-source hygiene.
- User lens: ordinary app user, ADHD, low tolerance for duplicate prose, strong preference for visual decision surfaces.
- Non-claim: tests and builds are only evidence. Visual/UX quality must be checked in rendered pages.

## Evidence So Far

- Memory recalled the existing Dashboard direction: ADHD-friendly triage, one judgment / one visual shape / one next step, repository controls out of main boards.
- Browser evidence: screenshots captured under `output/quality-review/20260511-0200/` for Inbox, Start, Profiles, Runs, and Settings at desktop 1440x1000 and mobile 390x844.
- Screenshot audit JSON: `output/quality-review/20260511-0200/screenshot-audit.json`.
- Reviewer B reported P1 documentation duplication across README / README.zh-CN / ROADMAP versus `docs/v0.5-alpha-alert-review-inbox.md`, plus a privacy-copy contradiction.

## Current Verdict

Cannot claim acceptance readiness yet.

The dashboard has a strong visual language, but Settings currently fails the ordinary app-user path: a long saved-source table appears before Add Sources, especially bad on mobile. The header also says tokens are never saved while Settings offers local credential-store save, which is a trust contradiction.

## Repair Roadmap

1. UI slice 1 - app-user noise and trust:
   - Put Add Sources before Saved Sources in Settings.
   - Reduce the initial saved-source page size so Settings does not start as a long source dump.
   - Fix token privacy copy to say secrets stay local / tokens are never shown, not never saved.
   - Align navigation language around Review instead of Inbox/Review split.

2. Docs slice 1 - single truth source:
   - Keep README focused on opening Signal Desk and basic app flow.
   - Move or collapse v0.5 monitor/Dashboard implementation detail into pointers to `docs/v0.5-alpha-alert-review-inbox.md`.
   - Keep ROADMAP at phase intent and exit criteria, not completed hardening logs.

3. UI slice 2 - mobile Review and Settings polish:
   - Re-test after slice 1.
   - Fix remaining touch targets below 44px where they are primary actions.
   - Re-check card text truncation and filter density on 390px mobile.

4. Verification / review loop:
   - After each slice: rebuild or typecheck, rerun focused tests, recapture screenshots, and triage reviewer reports.
   - Commit checkpoint when a slice is coherent and verified enough to roll back.

## Iteration 0 - Ground Truth And Plan

- Target: establish real page evidence and a non-duplicative plan before edits.
- Changes: added this iteration log and `docs/quality-task-state.md`.
- Verification: dashboard API healthy at `127.0.0.1:8765`; Vite app reachable at `127.0.0.1:5173`; screenshot set captured for 10 page/viewport combinations.
- External review: three same-workspace subagents launched; reviewer B completed with P1 docs/copy findings. Gate is degraded because this is not an external KIMI/GEMINI route.
- Triage: accept Settings ordering, privacy copy, naming alignment, and docs de-dup as first P1 fixes.
- Task state: planning; checkpoint not ready until UI slice 1 is implemented and verified.
- `needs_human`: final taste acceptance at user review.
- Residual risk: screenshots capture current local data shape; other private data shapes may reveal additional edge cases.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: screenshots and audit JSON kept under `output/quality-review/20260511-0200/` as evidence, not current docs.
- Next: implement UI slice 1.

## Iteration 1 - App-User Noise And Mobile Navigation

- Target: fix reviewer P0/P1 issues in mobile navigation, Settings source-wall ordering, and privacy copy.
- Changes:
  - `dashboard/src/styles/responsive.css`: mobile navigation is now a sticky top tab bar, not buried after long content; coarse mobile controls get larger hit areas.
  - `dashboard/src/components/settings.tsx`: Add Sources renders before Saved Sources; Saved Sources defaults to 8 rows instead of 24.
  - `dashboard/src/styles/settings/layout.css`: Settings grid now actually uses CSS grid, so source import and library can sit as action-first zones.
  - `dashboard/src/components/shell.tsx`: privacy copy changed from "Tokens are never saved" to "Secrets stay local."
  - `dashboard/src/main.tsx`: nav label aligned to Review; dialog focus restoration delayed to survive unmount cleanup.
  - `dashboard/src/styles/actions.css`: confirmation dialog secondary action is readable on the dark modal and buttons meet the 44px target.
- Verification:
  - `npm test -- --run`: 9 files / 67 tests passed.
  - `npm run build`: passed.
  - `python -m pytest -q`: 338 passed, 49 subtests passed.
  - `python -m ruff check .`: passed.
  - `git diff --check`: passed, with only line-ending warnings.
  - Screenshot evidence after repair: `output/quality-review/20260511-0225/mobile-settings.visible.png`, `mobile-review.visible.png`, and `mobile-start.visible.png`.
- External review:
  - Reviewer A reported P0 mobile nav buried after content, P1 Settings source wall, P1 Start hierarchy, P2 Runs summary.
  - Reviewer C independently reported P1 mobile nav, P2 touch targets, P2 modal focus/contrast.
  - Gate remains degraded because reviewers are same-workspace subagents, not external KIMI/GEMINI.
- Triage:
  - Accepted and fixed: mobile nav visibility, Settings action-first ordering, smaller source list, token copy contradiction, mobile touch-target gaps for primary controls, modal contrast/focus.
  - Deferred: Start one-next-step hierarchy and Runs decision summary. They remain next UI candidates after docs cleanup.
- Task state: checkpoint ready after deterministic and screenshot verification.
- `needs_human`: final visual acceptance remains user-owned.
- Residual risk: private source data with longer labels may still need visual sampling after the next UI slice.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: retained screenshot sets under `output/quality-review/` as raw evidence; current truth remains this log.
- Next: docs slice 1.

## Iteration 2 - README / ROADMAP Single Truth Source

- Target: remove duplicate v0.5 Dashboard rules from public docs while preserving ordinary user entry points.
- Changes:
  - `README.md`: collapsed v0.5 monitor detail to a Signal Desk app flow plus a short expert command appendix; removed live-delivery examples from the main path.
  - `README.zh-CN.md`: same cleanup in Chinese; changed the human flow from `Inbox / Runs` to `Review / Runs`.
  - `ROADMAP.md`: replaced detailed Dashboard hardening bullets with a pointer to `docs/v0.5-alpha-alert-review-inbox.md`; roadmap now keeps phase direction and exit criteria.
- Verification:
  - `rg` check found no remaining `delivery-mode live`, stale `Monitor & Inbox`, `Tokens are never saved`, or duplicated Dashboard hardening phrases in README / ROADMAP surfaces.
  - `git diff --check`: passed, with only Windows line-ending warnings.
- External review:
  - Directly addressed reviewer B P1 findings on README / ROADMAP duplication and live CLI path exposure.
- Triage:
  - Accepted: README / ROADMAP should point to v0.5 authority instead of mirroring it.
  - Covered: token save semantics now say local credential storage and no UI echo / SQLite / manifest / report / docs persistence.
- Task state: checkpoint ready after docs verification.
- `needs_human`: none for this slice.
- Residual risk: README is now less exhaustive; expert users must follow the linked agent contract or v0.5 authority for detail.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: no new raw artifacts.
- Next: UX slice 3, Start and Runs decision hierarchy.

## Iteration 3 - Start / Runs Decision Hierarchy

- Target: remove the ready-state "multiple equal next steps" problem called out by the UX reviewers.
- Changes:
  - `dashboard/src/components/actions.tsx`: ready-state Start now shows one recommended action. Pending Review cards win over scanning; scanning wins over automation. Other controls are collapsed.
  - `dashboard/src/main.tsx`: Start can open the Review tab directly when there are pending cards.
  - `dashboard/src/components/runs.tsx`: Runs now converts recent health into a decision summary, with failed runs and diagnostics above card volume.
  - `dashboard/src/styles/*`: mobile touch targets were tightened for Runs report links and delivery toggles; the Start next-action badge no longer stretches into a full-width stripe.
  - `tools/quality_visual_audit.py`: added a reusable real-browser screenshot/audit helper so later passes do not depend on one-off scripts.
- Verification:
  - `npm test -- --run`: 10 files / 71 tests passed.
  - `npm run build`: passed.
  - Real-browser screenshots and metrics: `output/quality-review/20260511-0240/`.
  - Mobile Start / Review / Runs / Settings: no horizontal overflow and zero small-target findings in the visual audit.
- External review:
  - Directly addressed reviewer A P1 Start hierarchy and P2 Runs summary.
  - Directly addressed reviewer C mobile touch-target follow-up for Runs report links and Settings delivery toggle.
- Triage:
  - Accepted: Start should prefer Review when cards are pending; delivery target setup is optional and must not seize the main path.
  - Accepted: Runs must state whether failures, diagnostics, or Review work should get attention first.
- Task state: checkpoint ready.
- `needs_human`: final taste acceptance remains user-owned.
- Residual risk: desktop compact controls remain below 44px where pointer precision is assumed; mobile audit is clean for the current data shape.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: screenshots and `visual-audit.json` retained under the timestamped evidence folder only.
- Next: UX slice 4, mobile Review density and long-title scan.

## Iteration 4 - Mobile Review Action Visibility

- Target: make the first Review card actionable within the mobile first viewport instead of making the user scroll through supporting detail first.
- Changes:
  - `dashboard/src/components/inbox.tsx`: added a mobile quick-action strip directly under the card title and rating.
  - `dashboard/src/styles/inbox.css` and `dashboard/src/styles/responsive.css`: mobile cards hide the duplicate lower action rail until profile-diff mode is opened; primary actions stay 44px+.
- Verification:
  - `npm test -- --run`: 10 files / 71 tests passed.
  - `npm run build`: passed.
  - Real-browser screenshots and metrics: `output/quality-review/20260511-0250/`.
  - Mobile Review: no horizontal overflow, zero small-target findings, and first-card actions visible above the reason/source/report detail stack.
- External review:
  - Addresses the ADHD/ordinary-user complaint that Review cards looked like reading material before they looked actionable.
- Triage:
  - Accepted: mobile users need action buttons before lower-priority evidence chips.
  - Preserved: desktop keeps the right-hand action rail and dense comparison layout.
- Task state: checkpoint ready.
- `needs_human`: final taste acceptance remains user-owned.
- Residual risk: very long private card titles may still push actions lower than desired; needs sampling with real data during acceptance.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: screenshots and audit JSON stay in the timestamped evidence folder.
- Next: Settings long-list disclosure and source-management copy.

## Iteration 5 - Settings Source List Progressive Disclosure

- Target: stop Saved Sources from becoming a default 82-row management wall on the ordinary Settings path.
- Changes:
  - `dashboard/src/components/settings.tsx`: Saved Sources now defaults to summary/search plus a deliberate "Show first 8" action. Search or topic filters still reveal matching rows immediately.
  - `dashboard/src/styles/settings/sources.css` and `dashboard/src/styles/responsive.css`: added a compact saved-source gate with mobile-safe layout.
- Verification:
  - `npm test -- --run`: 10 files / 71 tests passed.
  - `npm run build`: passed.
  - Real-browser screenshots and metrics: `output/quality-review/20260511-0305/`.
  - Mobile Start / Review / Runs / Settings: no horizontal overflow and zero small-target findings.
- External review:
  - Addresses reviewer A/B complaint that Settings opened as a source-management wall instead of an app-user task surface.
- Triage:
  - Accepted: source rows should be available on demand, not forced into the first Settings pass.
  - Preserved: search, topic filtering, and the first-page management list remain one click or one typed query away.
- Task state: checkpoint ready.
- `needs_human`: final taste acceptance remains user-owned.
- Residual risk: the 20260511-0300 screenshot run caught a transient local API error; 20260511-0305 re-run was healthy and is the evidence for this slice.
- Memory closeout: pending.
- Hook enforcement: manual.
- Artifact hygiene: invalid transient-error screenshots kept only as raw evidence; use 0305 as current visual reference.
- Next: desktop compact-control polish and local API error-state clarity.
