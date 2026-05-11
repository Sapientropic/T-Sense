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
matters. The current product center is **Signal Desk**: a browser dashboard for
setup, scanning, review, profile tuning, run health, and settings.

The first supported lane is developer opportunities: remote jobs, contracts,
paid engineering requests, and other time-sensitive posts that get buried in
Telegram channels.

## Demo

The 49-second demo video shows the T-Sense flow from noisy channels to a ranked
Signal Desk/report workflow.

<p align="center">
  <a href="docs/demo.mp4"><strong>Watch the T-Sense demo video</strong></a>
</p>

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
| `Start` | Connect Telegram, repair setup, run demo scans, and manage auto-scan controls. |
| `Review` | Triage the newest/highest-priority cards first, then teach future matching with Keep / Skip / Wrong match / Tune profile. |
| `Profiles` | Create profiles from plain language or files, edit matching rules, tune scan window and post limits. |
| `Runs` | See whether recent scans are healthy and open generated report artifacts. |
| `Settings` | Add sources, set AI/OCR keys, configure notifications, manage learning data, and check repository state. |

Signal Desk is still local-first. It does not store raw Telegram messages,
sessions, API keys, or bot tokens in dashboard state.

## Quick Start

### Windows

1. Install Python 3.12+.
2. Clone or download this repository.
3. Double-click `Signal Desk.bat`.
4. Keep the launcher window open while using the browser dashboard.

The launcher prepares the local Python environment, builds dashboard assets when
Node/npm is available, and opens Signal Desk on `127.0.0.1`. If port `8765` is
busy, it tries `8766-8799`.

### macOS / Linux

```bash
git clone https://github.com/Sapientropic/T-Sense.git
cd T-Sense
chmod +x setup.sh tgcs
./setup.sh
./tgcs dashboard --open
```

### First useful run

1. Open `Start` and create the offline demo report. This does not need Telegram
   login or an LLM key.
2. Connect Telegram using your `api_id` and `api_hash` from
   [my.telegram.org/apps](https://my.telegram.org/apps).
3. Add channel links or handles in `Settings -> Sources`.
4. Run a dry scan from `Start`.
5. Review cards in `Review`, then tune the profile when the results are too
   broad or too narrow.
6. Open `Runs` when something fails; it shows the next repair step before asking
   you to trust automation.

## Profiles

Profiles are Markdown files that describe what counts as signal. They can
include target roles, keywords, rejection rules, languages, source priorities,
and reporting preferences.

You can create and adjust profiles from Signal Desk:

- write a plain-language goal;
- import a Markdown, text, or PDF profile note;
- edit matching rules directly;
- apply profile suggestions generated from confirmed review feedback.

The built-in starter focuses on developer opportunities. Additional templates
cover market/news tracking, airdrops, research leads, and competitor monitoring.

## Reports

Every scan can produce a standalone HTML report with cards, source links,
decision labels, diagnostics, and run metadata.

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

Reports are written under `output/`; monitor runs use
`output/runs/<run_id>/`. Output files are local artifacts and are ignored by
Git.

## CLI for Agents

The short `tgcs` command remains the compatible CLI for humans and smoke tests:

```bash
./tgcs demo
./tgcs doctor --profile jobs
./tgcs login
./tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run
./tgcs dashboard --open
```

Agents and automation should use the JSON-oriented scripts and the contract in
[docs/agent-cli-contract.md](docs/agent-cli-contract.md). Keep raw Telegram
content in local artifacts, not in prompts, logs, or public docs.

Common lower-level commands:

```bash
python scripts/source_registry.py import-list channel_lists/jobs.txt \
  --source-registry .tgcs/sources.json --topic jobs --format json

python scripts/monitor.py run --profile-id jobs-fast \
  --delivery-mode dry-run --format json

python scripts/monitor.py feedback-export \
  --db .tgcs/tgcs.db --output output/feedback/review-feedback.jsonl --format json
```

## Privacy and Safety

- Telegram access uses MTProto through Telethon and only reads sources you can
  already access.
- Secrets stay local. `.tgcs/`, `output/`, sessions, logs, env files, and
  dashboard builds are ignored by Git.
- Signal Desk stores notification bot tokens in Windows Credential Manager when
  available, or uses environment variables for expert setups.
- Live delivery and live schedules remain explicit choices. The default path is
  dry-run first.
- The project is a local personal workflow tool. Use it in a way that respects
  Telegram's terms and the rules of the channels you read.

## Repository Map

| Path | Purpose |
| --- | --- |
| `Signal Desk.bat` | Windows app-style launcher. |
| `dashboard/` | React dashboard source for Signal Desk. |
| `scripts/` | Scanner, report, monitor, source registry, delivery, and dashboard server code. |
| `profiles/` | Markdown profile templates and starter profile config. |
| `channel_lists/` | Example channel-list inputs. |
| `templates/` | Report templates and demo fixtures used by `tgcs demo`. |
| `docs/agent-cli-contract.md` | Stable JSON/CLI contract for agents. |
| `docs/getting-api-credentials.md` | Telegram API credential guide. |
| `docs/tos-risk-analysis.md` | Terms-of-service and operational risk notes. |

## Development

```bash
python -m pytest -q
cd dashboard
npm test -- --run
npm run build
```

Use `python tools/quality_visual_audit.py <output-dir>` when changing dashboard
layout. It captures Start, Review, Profiles, Runs, and Settings across desktop
and mobile viewports and checks for horizontal overflow and small click targets.

## License

This project is licensed under AGPL-3.0 with a commercial licensing option. See
[LICENSE](LICENSE) and [docs/licensing.md](docs/licensing.md).
