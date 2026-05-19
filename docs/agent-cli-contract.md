# Agent CLI Contract

This document is the stable agent-facing contract for T-Sense v0.4
and the v0.5-alpha monitor/dashboard layer.
Human output remains best-effort prose; agents should use `--format json`.
The short `tgcs` facade is for humans and keeps defaults convenient; it does not
replace the explicit agent contract below.

Fixture-backed contract coverage lives under `tests/fixtures/contracts/`.
`tests/test_contract_fixtures.py` checks the shared agent envelope,
`semantic_items_v1`, `monitor_run_result_v1`, and a normalized
`run_manifest_v1` shape against those fixtures. Desk producer fixtures are
covered by focused `tests/test_desk_*_contracts.py` files. Dashboard sanitizer
fixtures are covered in `dashboard/src/domain/contract-privacy-fixtures.test.ts`,
`dashboard/src/domain/desk-settings-contract-fixtures.test.ts`, and
`dashboard/src/domain/sanitize.test.ts`. API client fixture gates live in
`dashboard/src/api/client-contract-fixtures.test.ts`. Add or update fixtures
with contract changes so Python emitters, TypeScript sanitizers, and API
clients do not drift silently.

## Envelope: `agent_envelope_v1`

JSON stdout uses this shape:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {
    "schema_version": "agent_envelope_v1"
  }
}
```

Failures use a routable error:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "registry_invalid",
    "message": "Source registry is invalid.",
    "retryable": false,
    "next_step": "Run source_registry.py validate and fix the registry.",
    "details": {}
  },
  "meta": {
    "schema_version": "agent_envelope_v1"
  }
}
```

Progress, diagnostics, and debug details must go to stderr in JSON mode.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime or provider error |
| 2 | Incomplete scan |
| 3 | Validation or configuration error |
| 4 | Auth or Telegram session error |

## Source Registry: `source_registry_v1`

Default path resolution:

1. `--source-registry`
2. `TGCS_SOURCE_REGISTRY`
3. `.tgcs/sources.json`

`.tgcs/` is private local state and ignored by git.

```json
{
  "schema_version": "source_registry_v1",
  "sources": [
    {
      "source_id": "telegram:cointelegraph",
      "username": "cointelegraph",
      "channel_id": null,
      "label": "Cointelegraph",
      "topics": ["market-news"],
      "priority": "normal",
      "expected_language": "en",
      "scan_window_hours": 24,
      "enabled": true,
      "notes": ""
    }
  ]
}
```

## Commands

Human-oriented facade:

```powershell
tgcs demo
tgcs init
tgcs init --starter jobs
tgcs quickstart jobs
tgcs doctor --profile jobs
tgcs login
tgcs run
tgcs run --profile market-news --hours 72
tgcs run --no-state
tgcs sources import channel_lists/example.txt
tgcs sources import channel_lists/jobs.txt --topic jobs
tgcs sources list --topic jobs
tgcs sources export --topic jobs --output output/jobs-sources.txt
tgcs monitor run --profile-id market-news
tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run
tgcs dashboard
tgcs dashboard --no-build
tgcs feedback export
tgcs schedule print --profile-id jobs-fast --interval-minutes 15 --delivery-mode dry-run
tgcs delivery test telegram-bot --chat-id 123456
tgcs bot install-menu
tgcs bot run
```

`tgcs demo` renders the offline fixture report to `output/demo-report.html`
without Telegram login or LLM provider keys. It is the preferred first
activation check before asking a human to configure credentials.
`tgcs init --starter jobs` uses the packaged public-source starter, writes the
human facade default profile as `jobs`, and imports those sources with `--topic
jobs` so the `jobs-fast` monitor lane is usable without first landing on
placeholder example sources. If `.tgcs/sources.json` already exists, the jobs
starter keeps real sources, prunes legacy `example_*` placeholders, and
non-destructively merges the packaged starter with the `jobs` topic tag.
`tgcs quickstart jobs` is read-only and prints one current expert command plus
one app-first next step for the Developer Opportunity starter: init, Settings >
Sources, doctor, login, first dry-run, or dashboard. It never starts login,
scanning, delivery, or scheduler installation. `--format json` is
credential-free and may be used by desktop smoke tests; consumers should treat
`next_command` as the CLI fallback and `next_app_step` as the human Signal Desk
guidance.
`tgcs run` defaults to `.tgcs/sources.json` when present, the local
`.tgcs/config.toml` profile when initialized, HTML output, `output/`, and v0.4
decision memory at `.tgcs/state`. Without local config the built-in fallback
profile remains `market-news`.
`tgcs sources import --topic <tag>` attaches topic tags to new sources and
merges them into existing matching sources; use `--topic jobs` before running
the `jobs-fast` profile against a topic-filtered registry.
`tgcs dashboard` serves the local Signal Desk dashboard and auto-builds the default
`dashboard/dist` assets when they are missing. When `--port` is omitted, it
uses `/api/desk/health` to reuse an existing compatible Signal Desk on 8765 or
auto-select the next free port through 8799. An explicit `--port` is strict and
fails with a human-readable error when occupied. `--no-build` skips asset
building for packaged/offline environments or custom static asset handling.
`--miniapp-only` serves only `/miniapp`, static assets, and `/api/miniapp/*`;
it must be used for public HTTPS tunnels instead of exposing the full dashboard.
In `--miniapp-only` mode, no-initData loopback preview is disabled by default so
public tunnels cannot depend on proxy headers for safety. Use
`--miniapp-allow-loopback-preview` only for local QA.
`--open` opens Signal Desk in the default browser after the server starts.
`tgcs bot install-menu` registers the Telegram Bot command menu with the saved
bot token. `tgcs bot run` installs that menu by default and starts a local
long-polling gateway. Bot messages are mapped to fixed local actions only:
status, latest, profiles, sources summary, Source assistant preview/apply, and
dry-run monitor scans. The gateway never accepts shell, file paths, argv,
tokens, raw Telegram message text, or live delivery commands from Telegram.
`tgcs bot install-miniapp-menu --url <https-url> [--text Review]` installs a
Telegram Mini App menu button. The URL must be public HTTPS and cannot be
localhost, loopback, or a private IP address. This command only registers the
Bot API menu URL; it does not provide hosting, webhook delivery, or a public
ingress. Add `--dry-run` to validate the URL/text and print the planned result
without loading the bot token or calling Bot API. The Mini App review shell is a
companion surface for already-created Review cards; it does not scan Telegram,
hold MTProto sessions, or serve raw message evidence.
Allowed chats come from
`TGCS_BOT_ALLOWED_CHAT_IDS`, explicit `--allow-chat-id`, or enabled Signal Desk
delivery targets in `.tgcs/tgcs.db`.
`Signal Desk.bat` is the Windows no-command-line launcher. `./signal-desk` is
the macOS/Linux app-like launcher; it runs setup on first launch, initializes
the default `market-news` starter when local defaults are missing, then starts
`./tgcs dashboard --open`.
Signal Desk `Start` is the primary human surface. It exposes a small dashboard
action API for human-friendly wrappers around fixed local commands:

- `GET /api/desk/health` returns `desk_health_v1` with app id, version, URL,
  and capability names, including `desk_bot_gateway_status_v1` when this Desk
  can report local Bot Gateway readiness. Launchers use it only to identify
  compatible local instances; it is not an agent execution contract.
- `GET /api/desk/actions` returns `desk_actions_v1`.
- `POST /api/desk/actions/<action_id>/run` returns `desk_action_result_v1`.
- Action IDs are server-side allowlist entries; request bodies are not command
  input.
- Execute-mode actions call `sys.executable scripts/tgcs.py ...` with
  server-side allowlisted argv. A small number of actions may substitute the
  server-selected profile id, but they never accept browser-supplied command
  strings, paths, or argv.
- Dry-run scheduler install/remove actions require an explicit confirmation
  body, then call only fixed server-side argv/files for the local dry-run task.
  Windows uses `schtasks.exe`, macOS uses a per-user launchd LaunchAgent, and
  Linux uses a `systemd --user` service/timer when available. The task identity
  stays stable, while install/preview commands choose the newest enabled
  `profiles/desk/*` profile before falling back to `jobs-fast`. They do not
  accept browser-supplied command strings, paths, or argv.
- `GET /api/desk/scheduler-status` returns `desk_scheduler_status_v1` by
  checking only that fixed dry-run task. The payload may include optional
  `platform`, `backend`, `profile_id`, `display_command`, `can_install`, and
  `can_remove` fields. It never returns raw scheduler output or local launcher
  paths.
- Dedicated Telegram setup/login endpoints handle the normal human login path
  from the browser: `/api/desk/telegram-status`,
  `/api/desk/telegram-credentials`, `/api/desk/telegram-login/send-code`,
  `/api/desk/telegram-login/verify-code`, and
  `/api/desk/telegram-login/cancel`.
- Dedicated notification token endpoints handle bot token presence without ever
  returning the token: `GET /api/desk/notification-token/status` returns
  configured/source/update metadata, and `POST /api/desk/notification-token`
  accepts only `{ "token": "..." }` or `{ "clear": true }`. Mutation requires
  loopback access. Environment variables win over local storage. Local desktop
  storage uses Windows Credential Manager on Windows and optional Python
  `keyring` backends on macOS/Linux; when no usable keyring exists, the product
  must clearly fall back to environment variables instead of pretending a save
  succeeded.
- Dedicated notification target endpoints handle the default Telegram Bot target
  without accepting command strings or tokens:
  `/api/desk/delivery-targets/telegram-bot-default` saves `chat_id/enabled`,
  and `/api/desk/delivery-targets/telegram-bot-default/test` always performs a
  dry run.
- Dashboard clients may route the live-delivery setup action to the Settings
  notification editor instead of running a `needs_human` action. That shortcut
  must not expose the action's CLI reference as a primary or problem-state UI.
  Start may summarize notification readiness from sanitized delivery targets as
  `Enabled`, `Muted`, or `Needs chat ID`, but should not render the chat id in
  that summary. Missing or muted notification states may show an app CTA that
  opens the Settings notification editor; it must not execute live delivery.
- Dedicated source import endpoints let Signal Desk accept pasted Telegram
  handles or `t.me` links without accepting file paths, commands, or argv:
  `/api/desk/sources/preview` validates and previews the default
  `.tgcs/sources.json` import, while `/api/desk/sources/import` writes to that
  fixed registry only.
- `POST /api/desk/sources/starter` installs the fixed packaged public-source
  starter list into `.tgcs/sources.json`. Packaged builds prefer
  `channel_lists/jobs.public-candidates.json` so safe recommendation metadata is
  preserved, while `channel_lists/jobs.txt` remains the handle-only CLI/fallback
  mirror. The endpoint accepts only an optional `topic`, prunes legacy
  `example_*` placeholder rows before adding starter sources, and must never
  degrade into a 0-source placeholder install.
- `POST /api/desk/sources/assistant` accepts a bounded natural-language
  instruction plus optional topic and `dry_run`; it extracts explicit Telegram
  handles/links locally, previews add/pause/resume/remove operations, then
  applies the same fixed registry mutations when `dry_run=false`. It does not
  accept paths, commands, argv, raw credentials, or arbitrary model output.
  `confirm_external_ai:true` may use the configured OpenAI-compatible provider
  only to classify already-saved source ids for pause/resume/remove; returned ids
  are validated against `.tgcs/sources.json` before any write.
- Dedicated saved-source endpoints let Signal Desk display and pause/resume the
  fixed workspace registry without accepting browser-supplied paths or commands:
  `GET /api/desk/sources` returns `desk_sources_v1`, and
  `POST /api/desk/sources/<source_id>/enabled` accepts only an `enabled`
  boolean and returns the refreshed source list.
- `POST /api/desk/sources/<source_id>/topics` accepts only a `topics` string
  list, validates short topic tags, writes the fixed `.tgcs/sources.json`
  registry, and returns the refreshed source list. It does not accept registry
  paths, commands, argv, tokens, or raw Telegram message data.
- `POST /api/desk/sources/<source_id>/remove` removes one validated source id
  after `{confirm:true}` and returns the refreshed source list.
- Desk actions separate registry syntax from real Telegram access.
  `sources_validate` runs the fixed source-registry syntax check.
  `sources_probe_access` uses the local Telegram session to run a bounded
  source-access probe, stores only safe labels/counts/reasons in
  `.tgcs/source-access-health.json`, and does not store Telegram message text.
  `sources_pause_inaccessible` and `sources_keep_accessible` require
  `{confirm:true}`, read only that recent health summary, and disable matching
  source ids in the fixed registry.
- Long-running Desk actions such as a practice scan or source-access probe are
  server-side locked. A second click returns a display result saying the action
  is already running instead of stacking another scan process.
- Live delivery, session access, raw Telegram message operations, and unsupported
  scheduler installation return guarded preview / `needs_human` or remain
  outside the action API. Non-systemd Linux remains a manual cron-preview path;
  the browser must not edit user crontabs.
- Sensitive Start endpoints require loopback access; non-loopback clients are
  blocked from running Desk actions, Telegram setup/login, notification target
  mutations, source import mutations, saved-source mutations, or dry-run
  scheduler changes.

Desk action result payloads are display summaries, not a second agent contract.
Agents should keep using CLI JSON output for automation.
Dashboard artifact links use `/artifacts/<url-encoded-path>` and are restricted
to report Markdown/HTML files under a workspace-local `runs/` directory.
Legacy `report.html` / `report.md` names and user-facing names such as
`developer-opportunity-signal-report-2026-05-09-1225.html` are allowed; traversal, non-run
paths, and raw scan artifacts are rejected. Dashboard surfaces should display a
human report name/category instead of exposing internal absolute paths. Legacy
generic report filenames should display as the profile report title plus
extension, not as `Reports/report.html` or `Reports/report.md`. If both
Markdown and HTML report artifacts exist for a run, the Dashboard projection must
use HTML as the default click target. Markdown-only report artifacts are served
as rendered HTML by the local artifact route.
`tgcs schedule print` is a no-side-effect helper: it prints a Windows Task
Scheduler, macOS launchd, Linux systemd-user, or cron preview for review and
never installs or starts a system task. `--platform auto` selects the current
machine's preferred preview; explicit `windows`, `launchd`, `systemd`, or `cron`
keeps output deterministic for docs and tests.
On Linux, `auto` selects systemd only when `systemctl` and a per-user runtime
are both present; headless or non-systemd environments stay on the cron preview.
When `--interval-minutes` is omitted, it previews the selected profile's
`work_interval_minutes`; an explicit `--interval-minutes` remains the override.
Signal Desk may install or remove only its fixed dry-run scheduler task after a
browser confirmation; this remains intentionally narrower than the expert CLI
schedule preview. The installed command follows the same current-profile
selection used by manual Desk dry-runs, but the OS task name is stable to avoid
orphaning old per-profile tasks.
Agents should call the lower-level commands when they need stable JSON output:

```powershell
python scripts/source_registry.py import-list channel_lists/example.txt --source-registry .tgcs/sources.json --format json --dry-run
python scripts/source_registry.py validate --source-registry .tgcs/sources.json --format json
python scripts/source_registry.py list --source-registry .tgcs/sources.json --format json
python scripts/source_registry.py export-list --source-registry .tgcs/sources.json --output output/generated-channels.txt --format json

python scripts/doctor.py --source-registry .tgcs/sources.json --profile profiles/templates/market-news.md --output-dir output --format json
python scripts/scan.py --source-registry .tgcs/sources.json --hours 24 --output output/scan.jsonl --format json
python scripts/report.py --input output/scan.jsonl --profile profiles/templates/market-news.md --output output/report.md --html-output output/report.html --source-registry .tgcs/sources.json --format json
python scripts/report.py --input output/scan.jsonl --profile profiles/templates/market-news.md --items-json output/extracted-items.json --state-dir .tgcs/state --feedback-jsonl output/report-feedback.jsonl --format json
python scripts/daily_report.py --source-registry .tgcs/sources.json --profile profiles/templates/market-news.md --html --state-dir .tgcs/state --format json
python scripts/monitor.py run --profile-id market-news --delivery-mode dry-run --format json
python scripts/monitor.py feedback-export --db .tgcs/tgcs.db --output output/feedback/review-feedback.jsonl --format json
```

`doctor.py` reports `dashboard_assets` and `miniapp_acceptance` as pass/warn
only; missing dashboard static files are not a hard failure because the human
`tgcs dashboard` facade can build `dashboard/dist` automatically when npm and
Node.js 20.19+ or 22.12+ are available. A built desktop `index.html` without the
Mini App `miniapp.html` entry is still a warning, and
`tgcs dashboard --miniapp-only` auto-builds when that Mini App entry is missing
from the default static bundle. `miniapp_acceptance` adds the local `/miniapp`
preview path, the miniapp-only tunnel command, and the menu-button dry-run
command so Mini App acceptance has an explicit no-side-effect checklist.
Channel-list
checks warn on duplicates and `t.me/+...` / `joinchat` invite-link references
so the human can replace them with usernames, numeric ids, or Telegram folder
import before the first real scan. Source-registry checks warn when all enabled
sources are `example_*` placeholders, because those examples are documentation
fixtures and will not resolve as real Telegram channels. For jobs-style
placeholder registries, the next step points first to Signal Desk Settings >
Sources and keeps `tgcs init --starter jobs --force` as an explicit reset path,
alongside the non-reset `tgcs sources import channel_lists/jobs.txt --topic jobs`
option. The
`llm_provider` check treats `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`,
`MINIMAX_TOKEN_PLAN_KEY`, and `MINIMAX_API_KEY` as valid provider credentials,
without echoing key values. For MiniMax, it reports the non-secret key type and
effective base URL so Token Plan CN routing is visible during first-run checks.

## Monitor Runner: `profile_run_config_v1`

v0.5-alpha adds a CLI-first monitor layer. It preserves existing scan/report
contracts and writes repeated-run state to `.tgcs/tgcs.db`.

Default config path: `.tgcs/profiles.toml`.

```toml
schema_version = "profile_run_config_v1"

[defaults]
output_dir = "output"
state_dir = ".tgcs/state"
database = ".tgcs/tgcs.db"
dashboard_url = "http://127.0.0.1:8765"

[[profiles]]
id = "market-news"
path = "profiles/templates/market-news.md"
enabled = true
source_registry = ".tgcs/sources.json"
source_topics = ["market-news"]
alert_rule = "high_new_or_changed"
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]

[[profiles]]
id = "jobs-fast"
path = "profiles/templates/jobs.md"
enabled = true
timezone = "Asia/Shanghai"
work_start = "09:00"
work_end = "23:00"
work_interval_minutes = 15
off_hours_interval_minutes = 60
scan_window_hours = 2
source_registry = ".tgcs/sources.json"
source_topics = ["jobs"]
alert_rule = "high_new_or_changed"
alert_max_age_minutes = 60
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]
prefilter_enabled = true
scan_concurrency = 3
scan_delay_seconds = 0.2
semantic_max_messages = 40
semantic_max_tokens = 6000
semantic_batch_size = 20
semantic_concurrency = 2
prefilter_keywords = [
  "hiring",
  "we're hiring",
  "is hiring",
  "job opening",
  "open role",
  "remote",
  "apply",
  "frontend",
  "front-end",
  "frontend engineer",
  "react",
  "vue",
  "typescript",
  "ui engineer",
  "web app",
  "webgl",
  "engineer",
  "developer",
  "freelance",
  "contract",
  "contractor",
  "gig",
  "bounty",
  "paid project",
  "mini app",
  "mini apps",
  "telegram mini app",
  "ton",
  "usdt",
  "budget",
  "招聘",
  "招人",
  "岗位",
  "职位",
  "远程",
  "外包",
  "兼职",
  "私活",
  "项目",
  "预算",
]

[[delivery]]
id = "telegram-bot-default"
type = "telegram_bot"
enabled = false
chat_id = ""
```

`scripts/monitor.py run` returns `agent_envelope_v1` with:

```json
{
  "schema_version": "monitor_run_result_v1",
  "status": "complete",
  "run_id": "run_20260508T090000Z_abcd1234",
  "manifest_path": "output/runs/run_20260508T090000Z_abcd1234/run-manifest.json",
  "db_path": ".tgcs/tgcs.db",
  "report_path": "output/runs/run_20260508T090000Z_abcd1234/developer-opportunity-signal-report-2026-05-08-0900.md",
  "html_path": "output/runs/run_20260508T090000Z_abcd1234/developer-opportunity-signal-report-2026-05-08-0900.html",
  "review_card_count": 3,
  "alert_count": 1,
  "prefilter": {
    "enabled": true,
    "keyword_count": 20,
    "matched_count": 4,
    "semantic_stage": "report_ran"
  },
  "semantic": {
    "max_messages": 40,
    "max_tokens": 6000,
    "batch_size": 20,
    "concurrency": 2
  },
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "thinking": "disabled",
    "usage": {
      "prompt_cache_hit_tokens": 17920,
      "prompt_cache_miss_tokens": 96
    },
    "cache": {
      "hit_rate": 0.9947
    }
  },
  "delivery_attempts": []
}
```

`scripts/monitor.py feedback-export` writes dashboard keep, skip, and
false-positive decisions as reusable `tgcs-feedback-v1` JSONL. It intentionally
exports empty `note` fields because dashboard notes may contain private workflow
context. It may include sanitized `rating` and `decision_status` fields so
14-day validation can measure false positives by priority and novelty without
exporting raw Telegram text. The human facade defaults to:

```powershell
tgcs feedback export
```

which reads `.tgcs/tgcs.db` and writes `output/feedback/review-feedback.jsonl`.

Run manifests use `run_manifest_v1`. They include profile/source hashes,
scan window, source filters, alert rule, alert schedule, prefilter status,
artifact paths, report status, alert count, error summary, executed commands,
and delivery attempts. Previous runs are kept under `output/runs/<run_id>/`;
only `output/latest/run-manifest.path` is updated as a pointer.

When `prefilter_enabled=true`, `monitor.py run` first calls `scan.py` and
performs local keyword matching. If no scanned message matches,
`data.status = "prefilter_no_match"`, `review_card_count = 0`, and no
`report.py`/LLM stage is called. If matches exist, they are written to
`prefiltered-scan.jsonl`; the report stage reads that filtered file while the
manifest keeps both raw and filtered scan artifacts.

SQLite stores dashboard state using these projections:

- `review_card_v1`: extracted item fields, source refs, card status, run refs.
  Display titles are placeholder-aware: `Unknown`, `Not specified`, and similar
  missing-value markers are not allowed to become the primary dashboard,
  alert, report, or feedback-export title when a more useful role/project/topic
  field is present in `item_json`. This read-time recovery also keeps legacy
  cards usable after display-title fixes.
- `alert_event_v1`: alert target, status, redacted payload, delivery result.
- `delivery_target_v1`: target id/type/enabled/config; never bot tokens.
  Dashboard projections also include `display_name`, `status_label`, and a
  short `detail` so the Settings tab can read as delivery state instead of raw
  config ids such as `telegram-bot-default`.
- `runs`: dashboard run projection, not the full `run_manifest_v1`. The state
  API keeps `run_id`, profile/status/timestamps, `review_card_count`,
  `alert_count`, `quality`, a human `display_name`, and one selected
  `report_artifact`; internal scan, metadata, registry, raw-scan, errors, and
  hash fields stay in run manifests and artifact tables instead of becoming the
  default Dashboard surface. HTML report artifacts take precedence over Markdown
  siblings for the Dashboard click target. UI visualizations should aggregate run health by day or another bounded window,
  and the visible run ledger should be capped by default; they should not
  require rendering one visual cell or always-visible row for every
  high-frequency monitor run.
- `dashboard_profile_v1`: profile display projection, not the full
  `profile_run_config_v1`. It includes `profile_id`, `display_name`,
  `display_path`, `enabled`, `alert_schedule_mode`, `source_topics`,
  `scan_window_hours`, `semantic_max_messages`, `delivery_target_count`, and
  `updated_at`; local absolute paths and full profile config stay internal.
- `profile_patch_suggestion_v1`: follow-up note, diff, proposed profile text.
  Dashboard projections include `profile_display_path`, placeholder-aware
  `card_title`, a short base hash, and apply readiness so the user can see
  which card created the pending profile diff and whether it is safe to apply
  without exposing machine-specific absolute paths as dashboard JSON fields.
- `source_stats`: dashboard projection of source channel value and latest-run
  yield. It includes all-time review-card counts, high-rate, alert counts, and,
  when the latest run has a `scan_meta` artifact, source-level `raw_count`,
  `kept_count`, `scan_keep_rate`, `latest_card_count`, `latest_high_count`, and
  `card_yield_rate`. It can also include `scan_failure`,
  `scan_failure_reason`, and `scan_incomplete` for latest-run access diagnosis.
  It also includes `display_name` so user-facing Dashboard labels do not have
  to expose snake_case Telegram handles as primary copy; the
  display label normalizes common technical initialisms and obvious channel-name
  typos. This projection reads only `scan.meta.json` source-health counters and
  must not copy raw Telegram message bodies into SQLite or the dashboard JSON.
- `source_insights`: dashboard projection of actionable source suggestions:
  `promote` for high-yield sources, `prune` for false-positive-heavy sources,
  `watch` for mixed medium-signal sources or latest-run sources with fresh
  messages but no review cards, `Access`/watch for sources whose latest scan
  failed, and `observe` for a source with one high signal that needs more sample
  size before promotion.
- `feedback_summary`: count of keep, skip, and false-positive feedback rows that
  can be exported as `tgcs-feedback-v1` JSONL, plus `by_action` counts for
  dashboard feedback distribution. It also includes `by_rating`,
  `by_decision_status`, a user-facing `next_action`, and redacted
  `recent_impacts` so Settings can show what is ready to export or review
  without opening exported JSONL or leaking feedback note bodies.
- `validation_summary`: 14-day behavior evidence for the Developer Opportunity
  loop. It includes run/card/action counts plus `triage_rate`, `keep_rate`, and
  `false_positive_rate` so the Dashboard can visualize whether the inbox is
  producing real decisions rather than just more cards.
- `setup_status`: first-use guidance for the dashboard empty state. Stable
  fields are `stage`, `next_step`, `has_profiles`, `has_runs`, and delivery
  booleans; `checks` is a display-oriented list with `check_id`, `label`,
  `status`, optional `detail`, and optional `command`. Commands are shown to the
  user for review and are not executed by the dashboard.
- `opportunity_summary`: latest-run first-screen projection with the profile
  `display_name`, scanned and prefilter-matched counts, high new/changed count,
  alert count, top ranked review cards, all-clear state, diagnostic counts,
  `decision_counts` for the latest run's new/changed/seen/recurring/expired
  cards, and a display-oriented `next_action` object with `label`, `detail`, and
  optional reviewable command.
  It is built from sanitized review-card projections and run manifests, not raw
  Telegram message bodies. When a run bypassed live scanning through
  `--scan-input`, the scanned and matched counts may fall back to
  `scan_meta.total_messages_collected` so replay/offline validation does not
  show a misleading `0/0` first-screen summary. Dashboard clients should render
  this as a compact judgment plus bounded funnel/health visualization; the
  summary is not a license to repeat the full report title or every top card on
  the first screen.
- `runs[*].quality`: dashboard run-quality projection with prefilter ratio,
  semantic stage, LLM provider/cache/latency, and report diagnostic counts.

Central SQLite state must not store Telegram sessions, API keys, bot tokens, or
raw Telegram message bodies. Follow-up notes are local workflow data; they do
not enter `item-memory.json` or future LLM prompts unless the user applies the
generated profile diff. Creating a follow-up profile diff requires a non-empty
note; empty generic follow-up rules are rejected to avoid polluting profiles.

HTML/Markdown reports use the same display-title helper as review cards. Custom
schema field labels are rendered for humans (`apply_url` -> `Apply URL`), and
URL-like fields are linked in HTML through the existing safe-link sanitizer.
Narrative fields such as `why` should not be duplicated in both the detail grid
and the explanatory body.

Decision-memory item keys also ignore those placeholder values for new writes.
For compatibility with existing local state, the enrichment path checks the
legacy placeholder-inclusive key once and migrates the entry to the cleaner key
instead of reclassifying the same item as brand new.

Default alert rule:

```text
rating == "high" and decision_state.status in ["new", "changed"]
```

Profiles may add `alert_max_age_minutes`. `jobs-fast` defaults to a 2-hour scan
window and `alert_max_age_minutes=60`, so missed scheduler ticks can be
recovered without interrupting the user for stale job posts. Dashboard profile
controls can pause or re-enable a profile, set `alert_schedule_mode` to
`work_hours`, `all_day`, or `muted`, and tune profile-specific runtime fields.
These are stored as local SQLite runtime overrides and applied by later monitor
runs. The profile enabled endpoint only accepts `{ "enabled": true | false }`
from localhost. The profile runtime settings endpoint accepts only this
allowlist from localhost: `scan_window_hours` in `1..168`,
`semantic_max_messages` in `1..500`, `timezone`, `workdays`, `work_start`,
`work_end`, `work_interval_minutes`, `off_hours_interval_minutes`,
`alert_rule`, and `alert_max_age_minutes`. `alert_rule` is limited to
`high_new_or_changed` and `high_new_only` for v0.5; the default remains
`high_new_or_changed`. These endpoints are Desk setting surfaces, not arbitrary
command or agent JSON execution contracts.

Profile diff apply/revert keeps the existing base-hash gate. A reverted diff
may be replayed through `POST /api/profile-patches/<patch_id>/replay` only when
the current profile still matches the revert snapshot. Replay creates a fresh
pending patch with a new `patch_id`; it never revives the old reverted patch.

Live alert suppression is status-aware: a sent `new` alert suppresses repeated
`new` delivery for the same card, but a later `changed` status remains eligible
for alerting when it still passes freshness and handled-card gates.
Telegram Bot alert text must stay phone-useful: title, priority, short reason,
and an original `t.me` message link when source refs can resolve one. It must
not show card ids or target ids as primary copy. Inline card action buttons are
only attached when the local Bot Gateway is running or an installed background
gateway was successfully restarted for callbacks; otherwise the alert tells the
user to update the card from Signal Desk Review.

For future provider-specific LLM optimization, keep semantic extraction prompts
cache-friendly: stable profile/schema/instructions first, incremental scan
messages last, and a stable cache key per monitor lane when the selected
provider supports one. Cache retention and pricing still need provider-specific
confirmation.

`report.py` must not pass the full scan metadata sidecar into the extraction
prompt. The LLM prompt uses a small allowlisted scan summary only: scan date,
window, source/message counts, failure/incomplete counts, and OCR flags.
Diagnostic fields such as `source_health`, run timestamps, cutoff times, output
paths, registry paths, and errors paths stay in artifacts/manifests, not in the
LLM prompt. Prompt message JSON is also minimized to extraction-relevant fields
such as `channel`, `id`, `date`, `text`, and resolved origin fields; runtime
debug fields like `sender_id`, media metadata, prefilter traces, and duplicate
message refs stay out of the provider request. `agent_extraction_request_v1`
uses the same minimized projection for `selected_messages` so agent fallback
work sees the same extraction surface as LLM mode.

For the high-frequency `jobs-fast` lane, keep semantic batches bounded with
`scan_concurrency=3`, `scan_delay_seconds=0.2`,
`semantic_max_messages=40`, `semantic_batch_size=20`,
`semantic_concurrency=2`, and `semantic_max_tokens=6000`. First-run and
backfill profiles may raise these further after real FloodWait/provider-limit
testing, but they should still aggregate into one report rather than streaming
partial alerts. Larger catch-up or exhaustive review should run as a
backfill/audit lane so interrupt latency does not depend on a noisy channel
burst.

When `OPENAI_API_KEY` is unavailable and `DEEPSEEK_API_KEY` is set,
`report.py` now defaults to `deepseek-v4-flash` at `https://api.deepseek.com`,
even when MiniMax is also configured. DeepSeek V4 calls set thinking mode to
disabled for the fast extraction lane and request JSON object output. JSON
responses include `data.llm`; monitor manifests carry the same `llm` projection
so cache hit/miss tokens and latency can be reviewed per run.

MiniMax M2.7 can be selected explicitly with `--model MiniMax-M2.7`. When
`MINIMAX_TOKEN_PLAN_KEY` is present, MiniMax defaults to the China-region
OpenAI-compatible endpoint `https://api.minimaxi.com/v1`; standard
`MINIMAX_API_KEY` defaults to `https://api.minimax.io/v1`. `MINIMAX_BASE_URL`
overrides both defaults.
MiniMax requests use `reasoning_split=true`, `temperature=0.01`, and
`max_completion_tokens` because the provider's OpenAI-compatible API separates
reasoning differently and rejects `temperature=0`.

Local provider/cache evaluation:

```powershell
python scripts/eval_deepseek_cache.py --sample-size 20 --repeat 3 --format json
python scripts/eval_deepseek_cache.py --sample-sizes 10,20,30 `
  --models deepseek-v4-flash,MiniMax-M2.7 --repeat 1 --max-tokens 1000 --format json
```

The single-run artifact uses `deepseek_cache_eval_v1`; matrix runs use
`deepseek_cache_eval_matrix_v1` for backward compatibility. Both store provider,
base URL, max token cap, aggregate usage, latency, selected source refs, source
counts, rating counts, and sanitized paths only. Workspace-local paths are
relative; external input paths are reduced to file names, with short hash
suffixes only when duplicate basenames would collide. They must not copy raw
Telegram message text or contact handles.

Telegram Bot delivery resolves the token from `TGCS_TELEGRAM_BOT_TOKEN` first,
then from the local OS secret store entry saved by Signal Desk Settings
(Windows Credential Manager or optional Python `keyring` backend).
Use `--delivery-mode dry-run` for tests and `--delivery-mode live` only when the
target chat id and token are intentionally configured.
Signal Desk `Settings` can save the default target `chat_id` and enabled/muted
state to local SQLite for non-CLI users. Monitor runs merge this Desk override
before writing targets back to SQLite, so a saved Desk target is not overwritten
by `.tgcs/profiles.toml` defaults. Signal Desk may save or clear the bot token
only through the local credential store API and never echoes token text in
responses, SQLite, manifests, reports, or docs.
Signal Desk may detect the default private chat id from Telegram Bot
`getUpdates` after the user has messaged the bot, or from the existing local
Telegram session user id. High-level summaries must continue to avoid rendering
raw chat ids.
The local Bot Gateway also uses `getUpdates` for ordinary desktop operation.
Webhook delivery remains outside this local contract until the hosted HTTPS
boundary is designed. The current Mini App contract is intentionally narrow:
`GET /api/miniapp/state` validates Telegram Mini App init data when present,
checks the saved chat/user allowlist, and returns `miniapp_review_state_v1`
with sanitized Review card projections only. Each card may include
`item.source_excerpt`, a short source/original-text excerpt with URLs replaced by
`[link]`; raw Telegram message fields remain outside the Mini App contract.
Card links use safe Telegram `source_refs` and must render as labeled actions,
not visible bare URLs. State may also include
`source_recommendations`, a metadata-only view of packaged public starter
sources with source id, channel, label, topic, reason, and whether that source is
already installed. Signed Telegram users do not receive local artifact paths;
loopback preview may include safe report links for desktop inspection.
State may include `learning_summary`, a Mini App-safe projection of Review
learning counts and next-action copy. It intentionally excludes local export
paths, raw recent-impact cards, profile text, and private feedback payloads, so
the Mini App can explain whether choices are ready for a profile draft without
becoming a profile editor.
`POST /api/miniapp/review-cards/<card_id>/action` accepts only `action` and
`note`, delegates to the existing `monitor_state.set_card_action()` or
`undo_card_action()` allowlist, and returns the same Mini App card projection
rather than the full local review-card row. `POST /api/miniapp/sources/starter`
accepts only `topic` and delegates to the same packaged starter-source import
used by Signal Desk, giving mobile users a one-tap way to refresh/add recommended
channels for the next local run.
If a public HTTPS tunnel is used, it must terminate at `tgcs dashboard
--miniapp-only`; ordinary dashboard APIs, artifacts, and local state routes are
not part of the public Mini App boundary. Mini-App-only mode requires signed
Telegram init data by default; `--miniapp-allow-loopback-preview` is reserved for
local QA. Forwarded remote clients without signed Telegram init data are
rejected even when the direct TCP peer is loopback, so a local tunnel cannot
silently fall back to preview authorization.
Signal Desk's Bot Gateway status projection includes only safe setup/run hints:
whether a token is configured,
allowed-chat counts and labels, background/autostart state, sanitized last
update/error text, and a `safe_next_action` string. It must not expose token
text, raw chat ids, raw Telegram message text, session paths, command strings,
or argv. Monitor live delivery may restart an already-installed background Bot
Gateway before attaching alert action buttons, but it must not create new
scheduler/autostart state without the user using Settings > Alerts.

Signal Desk `Settings` can also install starter sources, import pasted public
source links/handles or `public_source_candidates_v1` candidate JSON, and apply
bounded source assistant plans. Preview responses include a sanitized resolved
source plan; Apply posts that resolved plan back so the confirmed change is the
same change the user reviewed, even when AI source planning helped choose
sources. The browser body is limited to the documented fields; source registry
paths are fixed to `.tgcs/sources.json`, preview is no-write, and import reuses
`source_registry.py` normalization, topic merge, duplicate handling, and
validation. Candidate JSON is metadata-only: candidates may include channel,
handle, username, URL, title, language, topic, recommendation source, quality
hints, and notes. Import preserves safe title/language/recommendation metadata
as source label, expected language, and notes, and Settings displays/searches
that metadata. Message/post/raw text fields are rejected before preview or
import. The same Settings view can list saved sources, filter them by topic,
toggle only their `enabled` state, retag sources, and remove validated source
ids.

Source assistant has two planning lanes. Explicit pasted/import instructions may
add normalized Telegram channels from user-provided links or handles and may
pause/resume/remove only validated saved source ids. Local Telegram discovery
may enumerate visible user-session channels from all dialogs or one named/id
folder, sanitize that list to channel/title/label/folder metadata, and only
after `confirm_external_ai=true` send that metadata plus a bounded profile text
slice to the configured model. In discovery mode, AI `add` outputs are accepted
only when copied from `candidate_sources.channel`; existing-source operations
are accepted only when copied from saved `source_id` values. Signal Desk writes
only the fixed workspace-local registry and never accepts command strings, argv,
registry paths, raw Telegram message data, local paths, tokens, or Telegram
session material from the browser.

## Review Learning Paths

There are four related learning paths, and agents must keep them distinct:

- Review feedback events are the local source of truth for user judgement.
  `keep`, `skip`, `false_positive`, and `follow_up` are written to
  `feedback_events`; ordinary lifecycle actions such as `applied`, `saved`, and
  `dismissed` update the opportunity status but do not by themselves create
  profile-learning evidence.
- Profile patch suggestions are reviewable text diffs against the user's
  Markdown profile. They are created from sanitized feedback context, stay
  pending until approved, snapshot the current profile before apply, and can be
  reverted without hiding the generated profile text.
- Profile Coach is a preview layer. It may use the configured LLM only after the
  user asks for suggestions, otherwise it falls back to local rules. Its output
  is advice and candidate matching rules; it does not mutate a profile until the
  user creates and approves a draft.
- Feedback JSONL export is a private backup/decision-memory path, not the normal
  dashboard happy path. Exports should avoid raw note bodies and raw Telegram
  message text. Dashboard learning should prefer profile drafts and calibration
  evidence over asking users to inspect JSONL.

LLM matching in the current contract is prompt/structured-output semantic
extraction against the active profile. It is not an embeddings or vector-search
layer yet. Embeddings remain a future option only if post-review evidence shows
that prompt-based profile matching cannot separate recurring false positives
from high-value cards at acceptable cost.

## Human Login Boundary

Telegram login is human-owned. The normal path is Signal Desk `Start`, where the
user saves Telegram app credentials locally, requests a login code, enters the
code, and completes optional 2FA in the browser. Agents should not try to answer
phone/code/password prompts. When a JSON command returns
`telegram_session_unauthorized` or `telegram_login_interactive_required`, route
the task back to the human with Signal Desk `Start`.

Terminal fallback:

```powershell
tgcs login
```

`tgcs login` delegates to `scan.py --login-only`. In human mode it retries empty
or rejected phone numbers, verification codes, and 2FA passwords; typing `q`,
`quit`, `exit`, or `cancel` exits cleanly. In JSON mode, login never blocks on
stdin and returns an auth error instead.

## Agent Semantic Fallback

When no `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `MINIMAX_API_KEY`, or
`MINIMAX_TOKEN_PLAN_KEY` exists, `report.py --extractor auto` does not fail. It
writes a local request for the calling agent:

```powershell
python scripts/report.py --input output/scan.jsonl --profile profiles/templates/market-news.md --output output/report.md --extractor agent --write-extraction-request output/extract-request.json --format json
```

The success envelope uses `data.status = "agent_extraction_required"`:

```json
{
  "ok": true,
  "data": {
    "status": "agent_extraction_required",
    "request_path": "output/extract-request.json",
    "items_output_path": "output/extracted-items.json",
    "next_step": "Extract semantic_items_v1 JSON from request_path, write it to items_output_path, then rerun report.py with --items-json."
  },
  "error": null,
  "meta": {
    "schema_version": "agent_envelope_v1"
  }
}
```

The request file uses `agent_extraction_request_v1` and includes:

- `extraction_contract`
- `agent_instructions`
- `scan_meta`
- `selected_messages`
- prompt text for compatibility with existing profile behavior

The request file is the copyable data plane for extraction. It intentionally
omits local handoff paths such as `input_path`, `profile_path`,
`report_output_path`, and `items_output_path`; writable paths stay in the JSON
success envelope above, which is the local control plane.

The agent writes `semantic_items_v1`:

```json
{
  "schema_version": "semantic_items_v1",
  "items": [
    {
      "source_message_refs": [
        {
          "channel": "cointelegraph",
          "id": 123
        }
      ],
      "rating": "medium",
      "why": "Decision-relevant market signal"
    }
  ]
}
```

Then rerun:

```powershell
python scripts/report.py --input output/scan.jsonl --profile profiles/templates/market-news.md --items-json output/extracted-items.json --output output/report.md --html-output output/report.html --source-registry .tgcs/sources.json --format json
```

`--items-json -` reads the same schema from stdin. Items are validated against
the scan file; unknown `source_message_refs` return `items_json_invalid` with
exit code 3.

## Source Health

`scan.py` writes `source_health` into the metadata sidecar. v0.3 source health is
single-run evidence only:

- `raw_count`
- `kept_count`
- `oldest_message_at`
- `newest_message_at`
- `incomplete`
- `failure`
- `failure_reason`
- `ocr_count`

`report.py` can combine scan meta and the registry to produce single-run pruning
hints: `dormant`, `access_failed`, `incomplete`, `noisy_current_run`,
`duplicate_heavy_current_run`, and `valuable_current_run`.

## Decision Intelligence State

Decision intelligence is explicit opt-in for low-level agent commands. Agents
pass `--state-dir .tgcs/state` to `report.py` or `daily_report.py` when cross-run
memory is desired. The low-level default remains stateless. The human `tgcs run`
facade supplies `.tgcs/state` by default, with `--no-state` as the escape hatch.

Additional flags:

- `--state-dir PATH`: load and update local item memory at
  `PATH/item-memory.json`.
- `--state-read-only`: use local memory for labels and explanations, but do not
  write updates.
- `--feedback-jsonl PATH`: import exported `tgcs-feedback-v1` JSONL feedback.
  Repeat the flag for multiple files. This requires `--state-dir`.

The state file uses `item_memory_v1`:

```json
{
  "schema_version": "item_memory_v1",
  "updated_at": "2026-05-08T09:00:00Z",
  "items": {
    "profile:abc:topic:coinbase|event:exchange-outage": {
      "item_key": "profile:abc:topic:coinbase|event:exchange-outage",
      "profile_key": "profile:abc",
      "source_message_refs": [{"channel": "cointelegraph", "id": 101}],
      "first_seen_at": "2026-05-08T09:00:00Z",
      "last_seen_at": "2026-05-08T09:00:00Z",
      "seen_count": 1,
      "rating_history": [{"at": "2026-05-08T09:00:00Z", "rating": "high"}],
      "fingerprint": "sha256",
      "feedback_counts": {"keep": 1}
    }
  }
}
```

It must not contain raw Telegram message text, API keys, Telegram sessions, or
feedback note bodies.

Each enriched item can include `decision_state_v1`:

```json
{
  "schema_version": "decision_state_v1",
  "status": "new",
  "signals": ["new"],
  "semantic_cluster": "profile:abc:topic:coinbase|event:exchange-outage",
  "first_seen_at": "2026-05-08T09:00:00Z",
  "last_seen_at": "2026-05-08T09:00:00Z",
  "seen_count": 1,
  "explanations": {
    "novelty": "new",
    "match_confidence": "high",
    "urgency": "today",
    "source_priority": "high",
    "negative_evidence": "No official postmortem yet."
  }
}
```

Possible `status` values: `new`, `seen`, `changed`, `recurring`, and `expired`.
JSON report envelopes add `data.state_summary` and `data.items[*].decision_state`,
for example:

```json
{
  "state_summary": {
    "new": 1,
    "seen": 0,
    "changed": 0,
    "recurring": 0,
    "expired": 0,
    "total": 1
  },
  "items": [
    {
      "topic": "Coinbase",
      "event": "Exchange outage",
      "decision_state": {
        "schema_version": "decision_state_v1",
        "status": "new"
      }
    }
  ]
}
```
