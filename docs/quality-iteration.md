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

Cannot claim user acceptance yet; local evidence now supports a strong visual-quality checkpoint.

What is locally verified:
- Mobile Start / Review / Profiles / Runs / Settings are exactly one 390x844 viewport.
- Desktop Start / Review / Profiles / Runs / Settings are one viewport high.
- Latest full visual audit has no horizontal overflow and zero small-target findings across Start / Review / Profiles / Runs / Settings.

What blocks a stronger claim:
- Gemini reviewer route failed from rate limits.
- DeepSeek fallback task `7355855bc0fc` completed without repo access and is treated as weak/no-count signal.
- Human taste acceptance remains user-owned at the 2026-05-11 13:00 +08:00 review.

## Latest Evidence

- Latest full screenshot/audit set: `output/quality-review/20260511-0522-full-after-start/`.
- Latest affected-surface screenshot/audit set after KIMI full-surface P1 fixes: `output/quality-review/20260511-0600-kimi-full-p1-fix/`.
- Latest full screenshot/audit set after hiding empty profile drafts: `output/quality-review/20260511-0630-full-after-profiles-noise-cut/`.
- Latest full screenshot/audit set after removing Runs `none` noise: `output/quality-review/20260511-0645-full-after-runs-none-noise-cut/`.
- Latest full screenshot/audit set after compacting mobile Review: `output/quality-review/20260511-0700-full-review-density/`.
- Latest full screenshot/audit set with all mobile pages one-screen: `output/quality-review/20260511-0720-full-all-mobile-one-screen/`.
- Latest Settings yield summary screenshot/audit: `output/quality-review/20260511-0530-settings-yield-summary/`.
- Full reviewer packet: `output/quality-review/20260511-0522-full-after-start/reviewer-packet.md`.
- Current task state: `docs/quality-task-state.md`.

Latest deterministic checks:
- `npm test -- --run`: 12 files / 85 tests passed after the mobile Review density slice.
- `npm run build`: passed.
- `git diff --check`: passed, with only Windows line-ending warnings.

## Recent Checkpoints

- `940e584` - Settings source wall collapsed; Review action labels clarified.
- `b403a1e` - Qwen semantic feedback fixed; Runs count bars normalized across visible clusters.
- `1f85b0d` - Ready-mode Start secondary controls collapsed into one `More controls` disclosure.
- `0b32fb6` - Saved Sources collapsed summary now shows source yield from existing `source_stats`.
- `55d1b43` - KIMI full-surface P1 fixes: mobile Runs timeline labels are readable without wrapping, Review titles clamp on mobile, and Settings Repository uses human sync copy.
- `e8b1d23` - Profiles hides the empty `Preference Drafts = 0` panel and returns mobile Profiles to one viewport.
- `53af224` - Runs compact timeline no longer repeats `none` on empty days; the no-scan meaning remains in `aria-label` / tooltip.
- `c039f8a` - Mobile Review triage is a compact filter row and the first card fits in one viewport.
- Current slice - Mobile Runs is compacted to one viewport without reintroducing unreadable timeline labels.

## Latest Fixes

- Start:
  - Ready-mode users now see a hero, one recommended action, and one `More controls` disclosure.
  - Mobile Start dropped from 1161px to 844px.
- Review:
  - Secondary actions use `Wrong match` and `Tune profile` instead of insider shorthand.
  - Keep/Skip remain visually primary; tuning/mismatch actions are visually secondary.
  - Mobile card titles clamp to three lines before the action strip.
  - Mobile Review is now exactly 844px; the compact filter button keeps an accessible `aria-label`.
- Runs:
  - Recent evidence is grouped by attention/review/clean.
  - Multi-run report links state they are the latest report for one run in a cluster.
  - Count bars now use a shared visible scale so low-volume and high-volume clusters are visually comparable.
  - Mobile compact timeline dates are 11px and no longer split into unreadable fragments.
  - Empty days in the compact timeline show only the date instead of repeating `none`.
  - Mobile Runs is now exactly 844px; the repeated explanation under `Fix failed scans` is removed because the attention group already carries the action.
- Settings:
  - Sources / Alerts / Notes / Yield are top-level tasks.
  - Saved Sources defaults to a collapsed management entry.
  - Collapsed Saved Sources now shows existing yield facts such as `3 latest cards · 68 tracked`.
  - Mobile Settings task details are 11px, not 9px.
  - Repository collapsed summary now says `Workspace saved locally` / `Check when needed` instead of `UNCHECKED` / `--`.
- Profiles:
  - Empty preference drafts no longer render as a full panel.
  - Mobile Profiles is now exactly 844px instead of 917px.
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
- KIMI full-surface task `8d8822766019`: accepted P1s for Runs date readability, Review mobile title clamp, and Settings Repository human copy.
- Qwen structural review `0c5099e26020`: `pass-with-risks`; confirmed Claude plans P0/P1 are closed. Its Profiles 917px risk is stale because the current slice lowered Profiles to 844px.
- KIMI post-fix review `60b877b6c8ca`: `pass-with-risks`; P0/P1 are closed. Accepted its P2 `none` noise finding because it directly matched the user's repeated-noise constraint.

Degraded:
- Gemini task `fbec77e0e78b` failed from provider rate limit.
- DeepSeek task `7355855bc0fc` had no repo access; rated weak/no-count instead of treated as a reviewer pass.

## Residual Risk

- Full heterogeneous reviewer gate is still degraded because Gemini was rate-limited and DeepSeek lacked repo access.
- Source yield summary avoids fabricated timestamps; deeper recency wording needs a real timestamp field.

## Next Action

1. Commit the all-mobile-one-screen checkpoint.
2. Continue reviewer-driven polish only where evidence shows user-visible noise or interaction friction.
3. Near 2026-05-11 13:00 +08:00, stop opening new work and produce a concise evidence-backed handoff.
