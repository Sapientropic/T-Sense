# Desktop Platform Notes

T-Sense is local-first on Windows, macOS, and Linux. The dashboard path is meant
to feel app-like, while the CLI remains available for agents and advanced smoke
tests.

## Launchers

| Platform | Recommended launcher | Notes |
| --- | --- | --- |
| Windows | `Signal Desk.bat` | Creates or reuses `.venv`, prepares dependencies, then opens Signal Desk. |
| macOS / Linux | `./signal-desk` | Runs `setup.sh` on first launch, initializes the jobs starter when needed, then opens Signal Desk. |
| macOS Finder | `Signal Desk.command` | Thin double-click wrapper around `./signal-desk`. |

The expert path remains `./tgcs ...` on macOS/Linux and `tgcs.bat ...` on
Windows.

## Requirements

- Python 3.12+ is required.
- Node.js is optional when `dashboard/dist` is already present. A fresh source
  checkout needs Node.js 20.19+ or 22.12+ so Signal Desk can build its local UI.
- `setup.sh` can use `uv` to provision a managed Python when the system Python
  is too old.

If the dashboard needs a local build and Node/npm is missing or too old,
`./signal-desk` now stops with a direct install hint instead of surfacing a raw
launcher traceback.

## First-Run Sources

Signal Desk should not require a normal user to create source files by hand.
The app path is:

- `Use starter set` installs the packaged Developer Opportunity starter into
  `.tgcs/sources.json`.
- `Source assistant` accepts short instructions such as `add @remote_jobs` or
  `remove @old_jobs` and previews the local registry change before applying it.
- Saved sources can be paused, resumed, retagged, or removed from Settings.
- `Check source syntax` validates the registry file only. `Check source access`
  uses the local Telegram session to run a bounded, no-message-text probe and
  stores a source-health summary in `.tgcs/source-access-health.json`.
- After a source access check, Start can pause only inaccessible sources or keep
  only sources with recent readable messages. Both repair actions require an
  explicit confirmation and only disable sources; they never delete them.

External AI planning is opt-in because source names can be private. The offline
parser handles explicit Telegram handles and `t.me` links locally; when the user
enables AI planning, Signal Desk sends only saved source ids, labels, channels,
topics, and enabled state to the configured provider, then validates the returned
plan against the existing registry before applying anything.

## Local Secret Storage

Environment variables always win and remain the most portable fallback.

When local secure storage is available, Signal Desk can save API keys and bot
tokens into the current user's OS-backed store:

- Windows: Windows Credential Manager.
- macOS: Keychain through Python `keyring`.
- Linux desktop sessions: Secret Service or KWallet through Python `keyring`.

Headless Linux sessions, missing DBus/user services, or unavailable keyring
backends may not support local saving. In that case Signal Desk should report
that local storage is unavailable and ask for environment variables instead.

## Local Bot Gateway

After saving a Telegram bot token and chat target in Signal Desk Settings, a
desktop user can run:

```bash
./tgcs bot run
```

This installs the Telegram command menu on start and then uses Bot API long
polling from the local machine. Commands and natural-language messages are
mapped to fixed actions only: status, latest results, profile/source summaries,
dry-run scans, and confirmed Source assistant plans. The gateway needs local
Signal Desk state and does not make T-Sense available while the computer or
process is offline.

## Auto Scan

Signal Desk only installs or removes its fixed `jobs-fast` dry-run task after an
explicit browser confirmation. The browser never supplies scheduler paths,
commands, or argv.

| Platform | Backend |
| --- | --- |
| Windows | Task Scheduler through `schtasks.exe`. |
| macOS | Per-user `launchd` LaunchAgent. |
| Linux desktop/user session | `systemd --user` service and timer. |
| Non-systemd or headless Linux | Manual cron preview only. |

`tgcs schedule print` is no-side-effect and can print deterministic previews:

```bash
./tgcs schedule print --platform auto --profile-id jobs-fast --interval-minutes 15
./tgcs schedule print --platform cron --profile-id jobs-fast --interval-minutes 15
```

On Linux, `--platform auto` selects systemd only when `systemctl` and a per-user
runtime are both present. Otherwise it stays on the cron preview path.
