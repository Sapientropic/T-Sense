# TG Channel Scanner Roadmap

Last researched: 2026-05-09

This roadmap is market-informed, but it is still a product plan, not a
commitment log. Review note: product pages, Telegram platform rules, and
competitor positioning can change after the research date. Re-check the source
links before using this document for release notes, fundraising, pricing, or
legal positioning.

## Product Direction

TG Channel Scanner should become a local-first Telegram intelligence loop:

1. Read channels the user already subscribes to.
2. Apply a plain Markdown profile that describes what counts as signal.
3. Produce a ranked daily report with source evidence and raw context.
4. Keep privacy, cost, and Telegram platform risk visible by default.

The wedge is not "another Telegram feed." The wedge is "what should I act on
today, and why can I trust that answer?"

## Market Snapshot

### Broad Intelligence And Feed Readers

Examples: [Feedly](https://feedly.com/) and
[Inoreader](https://www.inoreader.com/features).

Strength: cross-source monitoring, RSS/newsletter/social aggregation, filtering,
and enterprise intelligence workflows.

Open gap: they are optimized for web-scale feeds and dashboards, not a local
MTProto scan of the user's subscribed Telegram channels with raw message
evidence.

### Source Conversion And Workflow Automation

Examples:
[RSS.app Telegram RSS](https://help.rss.app/en/articles/11060974-how-to-create-rss-feeds-from-telegram),
[Zapier Telegram integrations](https://zapier.com/apps/telegram/integrations),
and [Make Telegram Bot integrations](https://www.make.com/en/integrations/telegram).

Strength: convert public Telegram sources to RSS, route updates to
Slack/Discord/Telegram, and connect Telegram Bot events to other apps.

Open gap: they are plumbing. Users still need source curation, ranking, dedupe,
report semantics, and AI/provider privacy controls. RSS.app also documents a
public-channel limitation for Telegram RSS feeds.

### Telegram Analytics, Search, And Monitoring

Examples: [TGStat alerts](https://by.tgstat.com/en/alerts),
[Telemetrio](https://telemetr.io/en), and [TGStat](https://tgstat.org/).

Strength: public channel catalogues, keyword alerts, advertising analytics,
channel growth, and engagement metrics.

Open gap: they are strong for public-market monitoring and ads, but less suited
to private subscribed-channel review, daily decision reports, and
source-auditable personal workflows.

### Telegram AI Digest And Aggregator Tools

Examples: [Junction Bot AI Digests](https://www.junctionbot.io/ai-digests),
[Aggregaat](https://aggregaat.bot/), [Telebrief](https://telebrief.ti1orn.com/),
[tg-channel-digest](https://github.com/andrew-ld/tg-channel-digest), and
[Televizor](https://www.reddit.com/r/microsaas/comments/1sy0nl9/i_built_televizor_opensource_telegram_channel/).

Strength: these tools validate the core pain. Users follow too many
channels/chats, need digests, and often want private-channel support. Some tools
offer bot delivery, local Ollama, Docker, templates, or a unified feed.

Open gap: differentiate through profile-driven evaluation, ranked HTML/Markdown
artifacts, explicit source refs, local-first defaults, and safe media/AI upload
gates.

## User Pain Points

1. Telegram volume hides time-sensitive decisions.
   Users tracking jobs, tenders, crypto, local news, or business communities can
   easily face dozens of active chats and channels. Junction Bot explicitly
   sells against "1,000+ messages" and 5-minute review, while the Televizor
   creator describes channel switching and 100+ message/day channels as a core
   annoyance.

2. A chronological feed is still too much work.
   Aggregators solve "one place," but the user still has to decide what matters.
   TG Channel Scanner should rank by a profile and explain why a post is
   apply-worthy, investigate-worthy, duplicate, or rejected.

3. Private and member-only sources matter.
   Public RSS converters are useful, but RSS.app documents that Telegram RSS
   feeds are limited to public profiles/channels that do not require login. A
   Telethon/MTProto local scanner can serve subscribed/private channels the user
   can already access, while keeping session handling auditable.

4. Trust requires provenance.
   AI digests are useful only if the user can expand the original text, inspect
   the channel/message id, and understand why the item was included or skipped.
   Source identity, raw context, and scan completeness are product features, not
   just internal correctness.

5. Privacy and cost need explicit controls.
   Telebrief's Ollama/local path and self-hosting language show that privacy and
   vendor lock-in matter in this category. TG Channel Scanner should keep OCR,
   STT, full-video upload, and cloud LLM use opt-in and visible.

6. Automation tools leave too much glue work.
   Zapier and Make make routing easy, but they do not define the domain-specific
   scoring, profile schema, source health, dedupe, or daily review artifact.

## Positioning

Primary positioning:

> Local-first Telegram signal reports for people who monitor many channels but
> need a short, auditable daily decision list.

Best early users:

1. Job seekers and recruiters monitoring hiring channels.
2. Crypto, airdrop, and market watchers monitoring high-noise channels.
3. Analysts, researchers, and OSINT users who need evidence trails.
4. Founders, sales teams, and community managers watching leads, mentions, and
   competitor updates.
5. Personal news power users who already curate Telegram folders.

Non-goals for now:

1. Do not become a public Telegram search index.
2. Do not build a hosted SaaS until legal, privacy, and session handling are
   clearly designed.
3. Do not train, fine-tune, or resell datasets from Telegram data. As of
   2026-05-07, Telegram's API terms point to content licensing and AI scraping
   restrictions, so this remains a release-time review item.
4. Do not chase generic analytics dashboards unless users prove that channel
   metrics matter more than decision quality.

## Product Principles

1. Local-first by default.
   The scanner should remain useful without a hosted backend. Any cloud LLM,
   OCR, STT, or delivery integration should be explicit.

2. Source evidence before summary polish.
   A pretty digest is not enough. Every retained item should have a stable
   source key, raw text expansion, scan metadata, and a clear match reason.

3. Profiles are the product surface.
   Markdown profiles should become the way users encode goals, exclusions,
   scoring rubrics, language preferences, and output style.

4. Reports should be decision artifacts.
   HTML/Markdown outputs should support fast review, search, sharing, and later
   audit. The output is not just a debug artifact.

5. Safe defaults beat hidden power.
   Full-video upload, broad history scans, and third-party AI calls should stay
   behind explicit flags/config with documentation close to the option.

6. Low-friction control for repeated personal use.
   The product should help forgetful high-volume users act on signal without
   turning local automation into an enterprise approval workflow. Prompt/profile
   changes should be visible, reversible, and easy to apply.

## Current Design Entry

The detailed planning authority for the next delivery iteration is
[`docs/v0.5-alpha-alert-review-inbox.md`](docs/v0.5-alpha-alert-review-inbox.md).
Keep implementation-specific details there until the feature ships. This
roadmap should retain phase intent and exit criteria, not duplicate the full
dashboard, alert, or profile-editing contract.

## Roadmap

### v0.2 - Stabilize The Daily Decision Loop

Goal: make the current CLI reliable enough for repeated personal use.

Already in scope or recently addressed:

- Stable channel+message source identity for report items.
- Cutoff-aware scan completeness.
- Thumbnail-first standalone OCR defaults.
- Explicit scan output handoff in the daily pipeline.
- Focused tests and `pyproject.toml` tooling.
- Empty/no-useful-result diagnostics cover no messages, all filtered out,
  incomplete scans, OCR-disabled media, missing metadata, and provider
  availability boundaries.
- Offline `tgcs demo` renders `output/demo-report.html` without Telegram login
  or LLM keys, so first-run activation can start before credentials.
- First-run `doctor` checks for runtime dependencies, Telegram credentials,
  session state, source input, profile parsing, LLM provider keys, media
  dependencies, dashboard assets, and output directory permissions.
- `doctor` warns on channel-list duplicates and invite-link references before a
  real scan, so source import issues show up during first-run checks.
- `doctor` warns when the local source registry still contains only `example_*`
  placeholder sources, before monitor runs fail on unresolvable examples.
- `tgcs sources import <list> --topic jobs` can tag new sources and merge the
  same tag into existing matching sources, closing the `jobs-fast`
  topic-filtered import path.
- `tgcs init --starter jobs` now chooses `channel_lists/jobs.txt`, sets the
  human facade default profile to jobs, and imports with `--topic jobs`, so the
  developer-opportunity lane can avoid placeholder sources on first setup. When
  a source registry already exists, the jobs starter merges `channel_lists/jobs.txt`
  into it instead of skipping the topic import.
- `tgcs quickstart jobs` gives a read-only single next action for the Developer
  Opportunity starter, so users do not need to choose between init, doctor,
  login, dry-run monitor, and dashboard by reading multiple docs.
- `setup.sh` and `setup.bat` now call the jobs starter by default and print the
  jobs doctor + dry-run monitor path instead of routing first-time users back to
  placeholder market-news examples.
- Dashboard first-use and latest-run projections now keep the normal Review
  screen action-first: when latest actionable cards exist, the queue and triage
  bar are the summary; when there are no latest-action cards or source-access
  recovery is needed, the active board can show a compact latest-run signal
  brief, All Clear state, or severity-ranked top diagnostic. First Useful
  Report setup copy stays limited to empty/blocked/recovery states, and the
  14-day validation summary is folded evidence rather than a competing top-level
  report block.
- Dashboard Settings now distinguishes exportable keep/skip/false-positive
  feedback from follow-up notes that become reviewable profile diffs, so local
  feedback no longer looks like a blind total.
- Dashboard Settings now uses an action-first visual layout: source actions are
  the primary decision surface, Yield History now combines an all-source heatmap
  with compact top-source evidence, zero-value chips are suppressed, and
  exported files/reports use user-facing labels instead of raw internal paths.
  The Settings board is named around operations and counts only actionable
  delivery, feedback, and source-decision work rather than total tracked
  sources.
  Dashboard state now projects profiles and runs to display fields and
  report-only artifacts, keeping raw profile config, absolute paths, scan
  artifacts, registry paths, hashes, and target ids out of the default UI
  surface.
- Inbox review now includes a visual triage distribution bar plus view-only
  filters for all, high, new/changed, and low/medium cards so high-volume
  pending queues can be processed without adding risky bulk actions.
- Runs now use a fixed seven-day health chart for recent completion/failure and
  card/alert output, plus a capped recent evidence ledger, instead of one visual
  cell or always-visible row per run, so high-frequency monitoring does not
  crowd the desktop UI.
- Dashboard visual hierarchy has been tightened for ADHD-friendly use: repeated
  lane ids, long report names, repository controls, and explanatory prose are
  suppressed from the main Review/Runs boards unless they directly support the
  next action.
- Built-in profile templates cover jobs, airdrops, market/news, research leads,
  and competitor monitoring.

Next iterations:

- Tighten the first useful report path around real user source import:
  better folder import guidance and obvious rerun steps after `doctor` warnings.
- Make local feedback more visibly actionable: show which feedback rows have
  already influenced decision memory or a proposed profile diff.

Exit criteria:

- New user can produce a meaningful sample report in under 10 minutes.
- Reports explain all included and excluded high-confidence items.
- No silent reuse of stale scan files or ambiguous source ids.

### v0.3 - Source Operations

Goal: help users manage channels as durable sources instead of one-off text
lists.

Already in scope or recently addressed:

- Introduce a source registry with channel username/id, human label, topic,
  priority, expected language, scan window, and optional per-source notes.
- Import from Telegram folders or exported channel lists, then normalize into the
  registry.
- Show per-channel health: fetched count, kept count, filtered count, newest
  message time, oldest scanned time, incomplete flag, and last error.
- Add duplicate and forward-source handling so the same original post does not
  dominate the report.
- Add source pruning hints: noisy source, dormant source, repeated duplicate
  source, or source with frequent access failures.

Hardening focus:

- Keep Telegram folder import compatible with current Telethon response shapes,
  including wrapped `DialogFilters`, rich folder titles, and the default filter.
- Make source registry changes easier to review before they replace a user's
  existing private source list.
- Keep source health in the report connected to concrete next actions, not just
  counters.

Exit criteria:

- Users can understand which channels generated value and which created noise.
- Source list changes are reviewable and reversible.

### v0.4 - Decision Intelligence

Goal: move from summarization to durable signal detection.

Already in scope or recently addressed:

- Add local item memory for seen-before, changed, recurring, and expired leads.
- Add decision-state explanations for novelty, rating, urgency, source priority,
  and negative evidence.
- Support profile-specific report templates without changing scanner internals.

Planned work:

- Add cross-channel clustering so related posts collapse into one decision card.
- Extract structured entities per profile: company, role, location, deadline,
  token/project, person, event, product, or risk.
- Add negative evidence: why an item was skipped, not just why kept items were
  selected.

Hardening focus:

- Make the agent extraction handoff reliable when no LLM key is configured:
  request path, `semantic_items_v1` validation errors, and rerun instructions
  should be obvious in JSON and human-facing flows.
- Tighten feedback import/export so keep, skip, false positive, false negative,
  and short notes improve local decision memory without persisting raw note text.
- Improve empty-report diagnostics across the main failure modes: no messages,
  all filtered out, incomplete scan, OCR disabled for media-heavy sources, and
  unavailable LLM provider.
- Keep decision memory private and auditable: state should remain small, local,
  and free of raw Telegram message text, sessions, credentials, or note bodies.

Exit criteria:

- Daily reports reduce repeated items and highlight changes since the last run.
- Users can tune profiles without editing Python.

### v0.5 - Alert And Review Inbox

Goal: make the scanner a dependable repeated habit: high-priority new or
changed items can interrupt the user, while everything else goes into a local
review dashboard.

Alpha implementation is in active hardening:

- v0.5-alpha.1 adds `scripts/monitor.py run`, `profile_run_config_v1`,
  `run_manifest_v1`, SQLite-backed review cards/alert events/profile patch
  suggestions, private Telegram Bot delivery dry-run/live modes, and an
  optional Vite React dashboard served from `127.0.0.1`.
- v0.5-alpha.2 hardening is focused on four shipped workstreams: the Developer
  Opportunity fast lane (`jobs-fast` prefiltering, alert freshness, bounded
  semantic batches, provider/cache smoke history), the local review inbox
  (latest-action focus, triage distribution, feedback export, profile-diff
  visibility), source/run quality controls (Yield History evidence,
  source-health risk badges, run diagnostics, local report artifact links), and
  dashboard/report polish (human labels, placeholder-safe titles, compact
  first-use recovery, report-only run projections, and less machine-looking
  visual summaries).
- The existing v0.4 scan/report JSON contracts remain the agent-facing base.
  Dashboard state is local `.tgcs/tgcs.db` state, not a raw Telegram archive.
- A real `jobs-fast` run against imported jobs sources produced high-value
  cards and a report without requiring raw Telegram text in dashboard state;
  the current polish priority is now reducing activation friction and making
  source/report quality visible at first glance.

Remaining work before calling v0.5 done:

- Treat each profile as a durable monitoring task with its own schedule,
  working hours, source filters, alert rules, and delivery targets.
- Continue hardening follow-up-to-profile UX around already-collected local
  notes: make it obvious which accepted diff affected the next run and keep
  rollback/reapply boundaries visible.
- Make setup and packaging less brittle on Windows: one obvious install/check
  path, clearer Telegram source import guidance, and fewer manual rerun steps.
- Add optional webhook, email, or Telegram Saved Messages adapters only after the
  private Telegram Bot path proves stable in real use.
- Decide whether source-health trends need history beyond the current latest-run
  Yield History projection, or whether current promote/prune/watch/observe
  actions are enough for v0.5.

Deferred from v0.5 unless user evidence requires it:

- Per-source or per-topic profile binding.
- Snooze and mute-similar review actions.
- Rich source-health trend analysis beyond actionable warnings.
- Hosted, team, or multi-user dashboard features.
- True per-source scan watermarks.

Exit criteria:

- At least two profiles can run with different schedules and alert rules.
- The pipeline can run repeatedly without overwriting previous reports.
- Users can trace a delivered alert back to the full report and raw message.
- Follow-up feedback can become a confirmable profile diff that affects the next
  scan.
- The CLI remains usable without the dashboard.

### v0.6 - Packaging And Team Use

Goal: reduce setup friction and support small trusted teams without becoming a
hosted scraper.

Planned work:

- Provide `pipx`, `uvx`, and Docker installation paths.
- Harden the local dashboard for packaging, backup/restore, and small trusted
  team use.
- Add encrypted config/session guidance and backup/restore docs.
- Support multi-profile batch runs from the same channel registry.
- Add team-safe runbooks for shared profiles, local deployment, and third-party
  AI provider risk.

Exit criteria:

- A technical user can deploy the tool for a small team with a documented privacy
  model and repeatable setup.
- The CLI remains fully usable without the dashboard.

## Research Backlog

1. Interview 5-10 target users across job search, crypto/market monitoring,
   research/OSINT, community management, and personal news.
2. Compare first useful report time against Junction Bot, Aggregaat, Telebrief,
   Feedly/Inoreader, and a Zapier/Make workflow.
3. Validate whether users prefer daily reports, real-time alerts, or a hybrid.
4. Measure local LLM quality and cost tradeoffs against OpenAI/Anthropic/Gemini
   for the built-in profiles.
5. Re-check Telegram API terms, Bot API limitations, MTProto behavior, and AI
   scraping/content licensing rules before any public release.
6. Test whether source health and pruning hints are more valuable than a full
   dashboard for early users.

## Success Metrics

- Time to first useful report: under 10 minutes for a prepared channel list.
- Daily review time: under 5-10 minutes for 50+ channels.
- Source traceability: 100% of report items link to channel+message identity.
- Scan reliability: incomplete scans are explicit and below 5% after tuning.
- Quality loop: false positives and false negatives trend down after feedback.
- Privacy posture: no third-party upload of media or raw messages without an
  explicit config/flag.
- Product value: users keep at least one profile running weekly without manual
  prompt surgery.

## Source Notes

- [Feedly](https://feedly.com/) positions itself across news reading, market
  intelligence, and threat intelligence.
- [Inoreader features](https://www.inoreader.com/features) cover RSS, monitoring
  feeds, social listening, newsletters, global search, and website change
  tracking.
- [RSS.app Telegram RSS guide](https://help.rss.app/en/articles/11060974-how-to-create-rss-feeds-from-telegram)
  documents Telegram-to-RSS generation, automation uses, and the public-channel
  limitation.
- [Zapier Telegram integrations](https://zapier.com/apps/telegram/integrations)
  and [Make Telegram Bot integrations](https://www.make.com/en/integrations/telegram)
  represent the no-code automation category.
- [TGStat alerts](https://by.tgstat.com/en/alerts), [TGStat](https://tgstat.org/),
  and [Telemetrio](https://telemetr.io/en) represent public Telegram monitoring,
  search, advertising, and analytics tools.
- [Junction Bot AI Digests](https://www.junctionbot.io/ai-digests) and
  [Aggregaat](https://aggregaat.bot/) validate demand for Telegram digests,
  unified feeds, forwarding, and team-oriented monitoring.
- [Telebrief](https://telebrief.ti1orn.com/) and
  [tg-channel-digest](https://github.com/andrew-ld/tg-channel-digest) are close
  open-source references for Telethon-based AI digest workflows.
- [Televizor discussion](https://www.reddit.com/r/microsaas/comments/1sy0nl9/i_built_televizor_opensource_telegram_channel/)
  is useful community evidence for the "too many channels, one usable feed"
  pain.
- [Telegram API Terms](https://core.telegram.org/api/terms) remain a release-time
  checkpoint for content licensing and AI-scraping constraints.
