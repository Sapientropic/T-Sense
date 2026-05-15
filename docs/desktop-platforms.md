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
  only recently active sources. Quiet sources are readable but had no recent
  messages in the probe window. Both repair actions require an explicit
  confirmation and only disable sources; they never delete them.

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

Background mode and gateway liveness are separate checks. A login task can be
installed while the gateway is still `not_detected` or `stale`; Signal Desk
marks the gateway stale when its local heartbeat is older than 120 seconds. In
that state, use `Repair alerts` from Settings > Alerts. The repair
action restarts the installed Windows task, reloads the macOS LaunchAgent, or
restarts the Linux `systemd --user` service. If no scheduler backend is
available, run `./tgcs bot run` manually.

Live Telegram alerts include inline Review buttons only when the gateway can
handle callbacks. During monitor delivery, T-Sense may restart an already
installed background gateway before sending those buttons; if that cannot be
confirmed, the alert still includes the original Telegram message link and asks
the user to update the card from Signal Desk Review.

## Signal Desk Restart and Ports

The app launcher starts from `127.0.0.1:8765`. With the default auto-port mode,
it first reuses an already-running compatible Signal Desk discovered through the
local health endpoint. If the port is occupied by another local service, it
skips that port and tries `8766-8799`. Passing an explicit `--port` is strict:
the command fails instead of reusing or moving ports.

## Auto Scan

Signal Desk only installs or removes its fixed dry-run scheduler task after an
explicit browser confirmation. The browser never supplies scheduler paths,
commands, or argv. The task name stays stable across profile edits, but the
installed command follows the newest enabled `profiles/desk/*` profile before it
falls back to `jobs-fast`.

| Platform | Backend |
| --- | --- |
| Windows | Task Scheduler through `schtasks.exe`. |
| macOS | Per-user `launchd` LaunchAgent. |
| Linux desktop/user session | `systemd --user` service and timer. |
| Non-systemd or headless Linux | Manual cron preview only. |

On macOS, the auto-scan LaunchAgent runs the current virtualenv Python directly
with `scripts/tgcs.py monitor run ...`. It intentionally does not invoke the
repo-local `tgcs` shell launcher and does not set `WorkingDirectory`, because
LaunchServices sandbox/path inheritance can make shell launchers fail with
`bad interpreter` or `getcwd` errors. Turning auto review on again rewrites and
reloads the LaunchAgent, so a stale shell-based plist is repaired from Signal
Desk.

Signal Desk treats an installed macOS LaunchAgent as unhealthy when `launchctl
print` reports a failing job or a non-zero last exit code. The user-facing
Automation card should show repair guidance instead of implying that auto scan
is running normally.

`tgcs schedule print` is no-side-effect and can print deterministic previews:

```bash
./tgcs schedule print --platform auto --profile-id jobs-fast --interval-minutes 15
./tgcs schedule print --platform cron --profile-id jobs-fast --interval-minutes 15
```

On Linux, `--platform auto` selects systemd only when `systemctl` and a per-user
runtime are both present. Otherwise it stays on the cron preview path.
