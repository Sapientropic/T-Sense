# Signal Desk Quality Iteration

Current truth for the 2026-05-11 quality loop. The full historical log is archived at `docs/archive/quality-iteration-20260511-full-log.md`; this file stays short so future agents do not inherit stale labels or repeated noise.

## Operating Contract

- Mode: Integrity.
- Intake: user explicitly selected `1A2A3A`: continue useful slices until 2026-05-11 13:00 +08:00, use Integrity gate, and prioritize real page evidence over tests-only claims.
- Reviewer gate: use Orchestra `assign / poll / show / rate`; KIMI is required for devil-style UX/aesthetic/IA review. Gemini is rate-limited in this run and does not count as a pass.
- Scope: Signal Desk dashboard across desktop and mobile, plus docs truth-source hygiene.
- User lens: ordinary app user, ADHD, low tolerance for duplicate prose/noise, strong preference for visual decision surfaces.
- Non-claim: deterministic tests, build, and visual-audit metrics are evidence, not human acceptance.

## Current Verdict

Cannot claim acceptance readiness yet.

What is locally verified:
- Mobile Start and Settings are exactly one 390x844 viewport after the latest fixes.
- Mobile Review, Profiles, and Runs are still over one viewport but under 950px.
- Desktop Start / Review / Profiles / Runs / Settings are one viewport high.
- Latest full visual audit has no horizontal overflow and zero small-target findings across all audited tabs.

What blocks a stronger claim:
- Full-surface KIMI task `8d8822766019` is still pending.
- Gemini reviewer route failed from rate limits.
- DeepSeek fallback product task `7355855bc0fc` is pending.

## Latest Evidence

- Latest full screenshot/audit set: `output/quality-review/20260511-0522-full-after-start/`.
- Latest Settings yield summary screenshot/audit: `output/quality-review/20260511-0530-settings-yield-summary/`.
- Full reviewer packet: `output/quality-review/20260511-0522-full-after-start/reviewer-packet.md`.
- Current task state: `docs/quality-task-state.md`.

Latest deterministic checks:
- `npm test -- --run`: 11 files / 83 tests passed after the Settings yield-summary slice.
- `npm run build`: passed.
- `git diff --check`: passed, with only Windows line-ending warnings.

## Recent Checkpoints

- `940e584` - Settings source wall collapsed; Review action labels clarified.
- `b403a1e` - Qwen semantic feedback fixed; Runs count bars normalized across visible clusters.
- `1f85b0d` - Ready-mode Start secondary controls collapsed into one `More controls` disclosure.
- `0b32fb6` - Saved Sources collapsed summary now shows source yield from existing `source_stats`.

## Latest Fixes

- Start:
  - Ready-mode users now see a hero, one recommended action, and one `More controls` disclosure.
  - Mobile Start dropped from 1161px to 844px.
- Review:
  - Secondary actions use `Wrong match` and `Tune profile` instead of insider shorthand.
  - Keep/Skip remain visually primary; tuning/mismatch actions are visually secondary.
  - Mobile Review is 948px; this trade-off is accepted locally because clear labels beat cryptic compactness for the target user.
- Runs:
  - Recent evidence is grouped by attention/review/clean.
  - Multi-run report links state they are the latest report for one run in a cluster.
  - Count bars now use a shared visible scale so low-volume and high-volume clusters are visually comparable.
- Settings:
  - Sources / Alerts / Notes / Yield are top-level tasks.
  - Saved Sources defaults to a collapsed management entry.
  - Collapsed Saved Sources now shows existing yield facts such as `3 latest cards · 68 tracked`.
  - Mobile Settings task details are 11px, not 9px.
- Docs:
  - README / ROADMAP detail duplication was removed earlier.
  - Full quality history is archived; this file is the single current truth for the running loop.

## Reviewer Triage

Accepted and fixed:
- KIMI Runs timeline/evidence P0 from earlier rounds.
- KIMI Settings maze and mobile type-size concerns.
- Qwen Review action semantics and Settings `Yield` label correction.
- Claude Code plans report Runs P0/P1; remaining count-bar P2 was fixed in `b403a1e`.
- Qwen integrity warning that reviewer-packet claims needed pending-review wording.

Pending:
- KIMI full-surface task `8d8822766019`.
- DeepSeek fallback product task `7355855bc0fc`.

Degraded:
- Gemini task `fbec77e0e78b` failed from provider rate limit.

## Residual Risk

- Mobile Review/Runs/Profile pages remain taller than one viewport even though they are under 950px and have no overflow/small-target findings.
- Full heterogeneous reviewer gate is degraded until KIMI and one fallback product reviewer are read and triaged.
- Source yield summary avoids fabricated timestamps; deeper recency wording needs a real timestamp field.

## Next Action

1. Poll and triage KIMI task `8d8822766019`.
2. Poll and triage DeepSeek task `7355855bc0fc` if KIMI remains slow.
3. Update `docs/quality-task-state.md`, then continue the next reviewer-driven slice or final handoff when the deadline arrives.
