# Desktop Platform Notes

T-Sense is local-first on Windows, macOS, and Linux. The dashboard path is meant
to feel app-like, while the CLI remains available for agents and advanced smoke
tests.

## Launchers

| Platform | Recommended launcher | Notes |
| --- | --- | --- |
| Windows | `Signal Desk.bat` | Creates or reuses `.venv`, prepares dependencies, then opens Signal Desk. |
| macOS / Linux | `./signal-desk` | Runs `setup.sh` on first launch, initializes the default `market-news` starter when needed, then opens Signal Desk. |
| macOS Finder | `Signal Desk.command` | Thin double-click wrapper around `./signal-desk`. |

The expert path remains `./tgcs ...` on macOS/Linux and `tgcs.bat ...` on
Windows.

## macOS Packaged App Acceptance

The macOS packaged-app path uses a Tauri shell that starts the local Signal Desk
backend and serves the dashboard from app-owned state. Use the project-local
runner as the single build/run entrypoint:

```bash
./script/build_and_run.sh --verify
```

The verification mode rebuilds the dashboard, rebuilds the Tauri app, syncs the
backend runtime into `~/Library/Application Support/T-Sense/backend/`, copies
that runtime into `T-Sense.app/Contents/Resources/backend/`, launches the app,
and verifies the exact backend URL from the desktop log.

For acceptance smoke checks, run:

```bash
./script/macos_acceptance_check.py
```

This command verifies the local app bundle, app data root, desktop backend log,
health endpoint, loopback-only backend listener, action allowlist rejection,
demo report generation, artifact serving, local profile preview, support
diagnostics, app-owned user-state paths under
`~/Library/Application Support/T-Sense/`, packaged/app-owned backend runtime
paths, secret-free diagnostic export contents, the in-app real-scan readiness
checklist, named data-boundary and recovery guidance, secret/settings status
surfaces, saved-source surface, and dashboard state. It marks the real
profile/Telegram/source/report loop as `MANUAL` when user setup, credentials,
or authorized sources are not present.

During a full user acceptance session, create or select a profile, finish
Telegram login, add at least one authorized source, run one real report, then
run:

```bash
./script/macos_acceptance_check.py --full
```

`--full` fails until Telegram credentials/session, saved sources, a saved
profile, and at least one real run are present. Use the narrower flags
`--require-telegram`, `--require-sources`, `--require-profile`, and
`--require-run` when validating those gates one at a time.

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

- `Starter recommendations` installs the packaged public starter for the current
  topic into `.tgcs/sources.json`. The default first-run topic is `market-news`;
  the Developer Opportunity starter remains available when the user selects that
  profile/lane explicitly. Users should review and prune noisy channels from
  Settings before treating the list as production-quality.
- `Known public sources` accepts pasted public `t.me` links/handles or
  `public_source_candidates_v1` JSON. Candidate JSON is metadata-only and is
  rejected if it includes Telegram message/post/raw text fields; safe
  title/language/recommendation metadata is preserved in the source registry
  and shown in Saved Sources.
- `Source assistant` accepts short instructions such as `add @remote_jobs` or
  `remove @old_jobs` and previews the local registry change before applying it.
- `Source assistant` can also discover visible local Telegram channels from all
  dialogs or a named/id folder, then let the configured AI select channels
  against the active profile after explicit confirmation. It is shown after a
  profile exists; first-run users without a profile see starter/public source
  paths first.
- Saved sources can be paused, resumed, retagged, or removed from Settings.
- `Check source syntax` validates the registry file only. `Check source access`
  uses the local Telegram session to run a bounded, no-message-text probe and
  stores a source-health summary in `.tgcs/source-access-health.json`.
- After a source access check, Start can pause only inaccessible sources or keep
  only recently active sources. Quiet sources are readable but had no recent
  messages in the probe window. Both repair actions require an explicit
  confirmation and only disable sources; they never delete them.

External AI planning is opt-in because source names can be private. The offline
parser handles explicit Telegram handles, `t.me` links, and candidate-source
JSON locally. When the user enables AI planning for saved-source operations,
Signal Desk sends only saved source ids, labels, channels, topics, and enabled
state to the configured provider, then validates returned operations against the
existing registry. When the user enables AI planning for local channel/folder
discovery, Signal Desk sends only sanitized channel/title/label/folder metadata
plus a bounded profile text slice; AI additions are accepted only when copied
from the discovered candidate channel list.

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

## Telegram Mini App Review Shell

The Mini App is a companion review surface, not a new scanner. It reads
sanitized Review cards from the local monitor database, then writes only the
existing review actions back through the same `monitor_state` allowlist used by
Signal Desk. It never stores bot tokens, MTProto sessions, raw Telegram message
text, command strings, argv, or local file paths.

Local preview is available from the dashboard static bundle at `/miniapp` and
from Settings > Alerts via "Open Mini App preview". Telegram itself requires a
public HTTPS URL. The menu command only registers that URL with Bot API; it does
not host the app. Public tunnels must target the Mini-App-only boundary, not the
full Signal Desk dashboard:

```bash
./tgcs dashboard --miniapp-only --port 8778
./tgcs bot install-miniapp-menu --url https://example.com/miniapp --text Review
```

The Mini App API validates Telegram `initData` when present and checks the
saved bot chat/user allowlist. Full dashboard `/miniapp` loopback preview is
allowed for local development only. The `--miniapp-only` public boundary
requires signed Telegram init data by default; `--miniapp-allow-loopback-preview`
is reserved for local QA. Both state reads and action responses use the Mini App
card projection, so local row ids, run ids, timestamps used only for storage, and
raw decision explanations stay out of the mobile API. Signed Telegram users do
not receive local report artifact paths; those links are limited to full local
dashboard loopback preview. Forwarded remote clients still need signed Telegram
init data even if a tunnel connects to the local server over `127.0.0.1`.
Mobile cards include a safe `Original text` excerpt when available and show
Telegram source links as labeled "Open in Telegram" actions rather than visible
raw URLs. The same Mini App state includes packaged public source
recommendations, and `/api/miniapp/sources/starter` can add or refresh those
recommended channels for the next local run through the existing starter-source
import path.

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
repo-local `tgcs` shell launcher, because LaunchServices sandbox/path
inheritance can make shell launchers fail with `bad interpreter` or `getcwd`
errors. Turning auto review on again rewrites and reloads the LaunchAgent, so a
stale shell-based plist is repaired from Signal Desk.

LaunchAgent stdio logs must stay in the pre-created `/tmp/tsense-launchd-*`
directory. `launchd` opens `StandardOutPath` and `StandardErrorPath` before it
execs Python; moving these paths back under the project can make repair appear
successful while the job immediately exits with `EX_CONFIG` before application
stderr exists.

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
