<div align="center">

<p>
  <img src="docs/brand/wordmark.png" alt="T-Sense pixel wordmark" width="860">
</p>

<h3>Your next signal is already in the noise. T-Sense brings it to the surface.</h3>

<p>
  <a href="README.zh-CN.md"><strong>中文文档</strong></a>
  ·
  <a href="#signal-desk"><strong>Signal Desk</strong></a>
  ·
  <a href="#demo"><strong>Demo</strong></a>
  ·
  <a href="#quick-start"><strong>Quick Start</strong></a>
  ·
  <a href="#cli-for-agents"><strong>CLI for Agents</strong></a>
  ·
  <a href="#privacy-and-safety"><strong>Privacy</strong></a>
  ·
  <a href="ROADMAP.md"><strong>Roadmap</strong></a>
</p>

</div>

T-Sense reads Telegram channels you already have access to, scores the messages
against a Markdown profile, and gives you a local workflow for reviewing what
matters. It works as a general signal workflow with built-in templates for
market/news tracking, airdrops, research leads, competitor monitoring, and
developer opportunities.

**Signal Desk** is the local browser dashboard inside T-Sense. It handles setup,
scanning, review, profile tuning, run health, and settings without turning the
normal user path into a CLI checklist.

## Demo

The 49-second demo video shows the T-Sense flow from noisy channels to a ranked
local signal brief.

https://github.com/user-attachments/assets/cf69300b-85cf-49b2-ab15-a0320945115c

## Signal Desk

Signal Desk runs on `127.0.0.1`. It keeps setup and review in the app so a
normal user does not have to edit TOML, copy JSON, or remember CLI commands.

<p align="center">
  <img src="docs/screenshots/signal-desk-start.png" alt="Signal Desk Start tab" width="860">
</p>

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/signal-desk-review.png" alt="Signal Desk Review tab">
    </td>
    <td width="50%">
      <img src="docs/screenshots/signal-desk-profiles.png" alt="Signal Desk Profiles tab">
    </td>
  </tr>
</table>

### What you can do in the dashboard

| Tab | Purpose |
| --- | --- |
| `Start` | Run the demo, create a goal/profile, connect Telegram, add sources, and start the first review. |
| `Review` | Triage the newest/highest-priority cards first, mark opportunity state with Applied / Saved / Contacted / Duplicate / Dismissed, then tune future matching with Prefer similar / Deprioritize / Wrong match. |
| `Profiles` | Create profiles from plain language or files, edit matching rules, tune scan window and post limits. |
| `Runs` | See whether recent scans are healthy and open generated report artifacts. |
| `Settings` | Add or prune sources with starter sets, pasted public links/handles, candidate JSON, or Source assistant, set AI/OCR keys, configure notifications, manage learning data, and check repository state. |

Signal Desk is still local-first. It does not store raw Telegram messages,
sessions, API keys, or bot tokens in dashboard state.

After saving a Telegram bot token and chat in Settings, you can also run the
local Bot Gateway:

```bash
./tgcs bot run
```

The bot can show status, run dry scans, summarize the latest results, and
preview source changes. It installs its Telegram command menu on start, and
source changes still require an Apply confirmation.

T-Sense also includes a Telegram Mini App review companion shell. It reuses
already-generated local Review cards for Applied / Save / Not a fit / Feedback
actions; it does not scan Telegram, hold sessions, or store raw message text.
The local dashboard can preview it at `/miniapp`, and Settings > Alerts includes
an "Open Mini App preview" shortcut. Installing the Telegram menu button only
registers a URL; it does not host the app. If you expose a local server through
a public HTTPS tunnel, run a Mini-App-only boundary and tunnel that port, not
the full Signal Desk dashboard. The Mini-App-only boundary requires signed
Telegram init data by default; `--miniapp-allow-loopback-preview` is only for
local QA, not public tunnels:

```bash
./tgcs dashboard --miniapp-only --port 8778
./tgcs bot install-miniapp-menu --url https://example.com/miniapp --text Review --dry-run
./tgcs bot install-miniapp-menu --url https://example.com/miniapp --text Review
```

Background mode only means the local scheduler is allowed to start the gateway.
If Settings shows the gateway as stale or not detected, use
`Restart / repair bot` from Settings > Alerts. It restarts the installed local
background task when one exists; `./tgcs bot run` remains the manual fallback.

## Quick Start

Requirements:

- Python 3.12+.
- Node.js 20.19+ or 22.12+ when you want the dashboard assets built locally.

### Windows

1. Install Python 3.12+.
2. Clone or download this repository.
3. Double-click `Signal Desk.bat`.
4. Keep the launcher window open while using the browser dashboard.

The launcher prepares the local Python environment, builds dashboard assets when
Node.js 20.19+ or 22.12+ with npm is available, and opens Signal Desk on
`127.0.0.1`. It reuses an existing compatible Signal Desk when one is already
running; if port `8765` is occupied by something else, it tries `8766-8799`.

### macOS / Linux

```bash
git clone https://github.com/Sapientropic/T-Sense.git
cd T-Sense
chmod +x setup.sh tgcs signal-desk "Signal Desk.command"
./signal-desk
```

`./signal-desk` is the recommended app-like launcher. On macOS you can also
open `Signal Desk.command` from Finder. Use `./tgcs ...` directly only when you
want the expert CLI path.

Platform-specific notes for local key storage and auto-scan setup live in
[docs/desktop-platforms.md](docs/desktop-platforms.md).

### First useful run

1. Open `Start` and create the offline demo report. This does not need Telegram
   login or an LLM key.
2. Create or select a monitoring goal from `Profiles` / `Start` so Signal Desk
   knows what you want to watch.
3. Connect Telegram using your `api_id` and `api_hash` from
   [my.telegram.org/apps](https://my.telegram.org/apps).
4. Add and check sources from `Start` / `Settings -> Sources` with the curated
   public starter set, pasted public links/handles, metadata-only candidate
   JSON, or Source assistant. Source assistant can preview local Telegram
   folder/all-channel discovery before applying any registry change.
5. Run a dry scan from `Start`; if access fails, use the source access repair buttons before scanning again.
6. Review cards in `Review`, then tune the profile when the results are too
   broad or too narrow.
7. Open `Runs` when something fails; it shows the next repair step before asking
   you to trust automation.

## Profiles

Profiles are Markdown files that describe what counts as signal. They can
include topics, tracked entities, keywords, rejection rules, languages, source
priorities, and reporting preferences.

You can create and adjust profiles from Signal Desk:

- write a plain-language goal;
- import a Markdown, text, or PDF profile note;
- edit matching rules directly;
- apply profile suggestions generated from confirmed review feedback.

Review choices are part of the learning loop. Applied, Save, Not a fit, and
Feedback actions can produce a reviewable profile draft; applying or reverting
that draft changes future matching without hiding the profile text from you.
Today the semantic matcher is profile-first LLM extraction, not a vector index:
Review feedback tunes the Markdown profile and calibration evidence shows
whether the next run improved.

Built-in templates cover market/news tracking, airdrops, research leads,
competitor monitoring, and developer opportunities. `market-news` is the default
starter; `jobs-fast` is available when you specifically want the developer
opportunity lane.

## Output and Review Cards

Every scan can produce a standalone dark-theme HTML report with cards, source
links, decision labels, diagnostics, and run metadata. Report titles and labels
come from the active profile, so a market brief, research brief, and job report
do not need to look like the same workflow.

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/report-header.png" alt="Generated report header">
    </td>
    <td width="50%">
      <img src="docs/screenshots/report-cards.png" alt="Generated report cards">
    </td>
  </tr>
</table>

T-Sense keeps generated artifacts out of Git:

| Path | What belongs there | Desk behavior |
| --- | --- | --- |
| `output/runs/<run_id>/` | Monitor runs, replay imports, reports, manifests, scan sidecars. | Creates or updates Review cards and keeps report evidence openable. |
| `output/<name>` | Demo reports, one-off manual reports, feedback exports, screenshots, evals. | Opens report/brief files, but does not create Review cards by itself. |

If a historical or manual scan should appear in Review, run it through the
monitor lane with `tgcs monitor run --scan-input ...`. The full artifact contract
lives in [docs/output-artifacts.md](docs/output-artifacts.md).

## CLI for Agents

The short `tgcs` command remains the compatible CLI for humans and smoke tests:

```bash
./tgcs demo
./tgcs doctor --profile market-news
./tgcs login
./tgcs monitor run --profile-id market-news --delivery-mode dry-run
./tgcs dashboard --open
```

Agents and automation should use the JSON-oriented scripts and the contract in
[docs/agent-cli-contract.md](docs/agent-cli-contract.md). Keep raw Telegram
content in local artifacts, not in prompts, logs, or public docs.

Common lower-level commands:

```bash
python scripts/source_registry.py import-list channel_lists/example.txt \
  --source-registry .tgcs/sources.json --topic market-news --format json

python scripts/monitor.py run --profile-id market-news \
  --delivery-mode dry-run --format json

python scripts/monitor.py feedback-export \
  --db .tgcs/tgcs.db --output output/feedback/review-feedback.jsonl --format json
```

## Privacy and Safety

- Telegram access uses MTProto through Telethon and only reads sources you can
  already access.
- Secrets stay local. `.tgcs/`, `output/`, sessions, logs, env files, and
  dashboard builds are ignored by Git.
- Signal Desk uses local OS-backed secret storage when available. Environment
  variables remain the reliable expert fallback.
- Live delivery and live schedules remain explicit choices. The default path is
  dry-run first.
- The project is a local personal workflow tool. Use it in a way that respects
  Telegram's terms and the rules of the channels you read.

## Repository Map

| Path | Purpose |
| --- | --- |
| `Signal Desk.bat` | Windows app-style launcher. |
| `signal-desk` / `Signal Desk.command` | macOS/Linux app-style launchers. |
| `dashboard/` | React dashboard source for Signal Desk. |
| `scripts/` | Scanner, report, monitor, source registry, delivery, and dashboard server code. |
| `profiles/` | Markdown profile templates and starter profile config. |
| `channel_lists/` | Example channel-list inputs. |
| `templates/` | Report templates and demo fixtures used by `tgcs demo`. |
| `docs/desktop-platforms.md` | Desktop launcher, key storage, and auto-scan platform notes. |
| `docs/output-artifacts.md` | Local `output/` artifact lanes, Desk-openable report paths, and cleanup policy. |
| `docs/agent-cli-contract.md` | Stable JSON/CLI contract for agents. |
| `docs/needle-local-command-router-research.md` | Research note on Cactus Needle as a local Bot Gateway intent router. |
| `docs/technical-debt-cleanup-spec.md` | Current technical-debt authority and documentation ownership map. |
| `docs/quality/task-state.md` | Compact current quality handoff; read it after the debt authority. |
| `docs/quality/2026-05-13-tech-debt-iteration-log.md` | Historical cleanup evidence, not current state authority. |
| `docs/testing.md` | Canonical local testing and quality-gate commands. |
| `docs/getting-api-credentials.md` | Telegram API credential guide. |
| `docs/tos-risk-analysis.md` | Terms-of-service and operational risk notes. |

## Development

Use [docs/testing.md](docs/testing.md) as the canonical local testing and
quality-gate command index. It also covers staged-index verification for dirty
worktrees.

Use [docs/technical-debt-cleanup-spec.md](docs/technical-debt-cleanup-spec.md)
for current debt status. [docs/quality/task-state.md](docs/quality/task-state.md)
is only the compact active handoff, and dated quality logs are evidence records.

## License

This project is licensed under AGPL-3.0 with a commercial licensing option. See
[LICENSE](LICENSE) and [docs/licensing.md](docs/licensing.md).
