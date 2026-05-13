# Testing And Quality Gates

This is the canonical local command index for repository verification. CI is
still the platform authority; these gates are the expected local evidence before
committing or asking for review.

## Rules

- Run focused tests first for fast feedback, then run the broader gate that
  matches the change risk.
- In a dirty worktree, mixed working-tree tests do not prove the commit. For a
  checkpoint commit, verify the staged index or a clean `HEAD` archive.
- Credential-free and dry-run paths are the default. Live Telegram, LLM, and
  notification delivery checks require explicit operator intent.
- Contract changes must update fixture coverage before being called stable.

## Fast Contract And Privacy Gate

Use this for schema, sanitizer, privacy, report-contract, and dashboard-boundary
changes:

```powershell
python -m pytest tests/test_contract_fixtures.py tests/test_report_contracts.py tests/test_contract_privacy_fixtures.py tests/test_dashboard_state_contracts.py tests/test_desk_contract_fixtures.py tests/test_desk_source_access_contracts.py tests/test_agent_semantic_fallback.py tests/test_report.py -q
```

```powershell
Push-Location dashboard
npm test -- --run contract-privacy-fixtures dashboard-state-contract-fixtures desk-contract-fixtures desk-source-access-contract-fixtures client-contract-fixtures sanitize client
Pop-Location
```

## Medium V0.5 Backend Gate

Use this for monitor, dashboard server, bot gateway, and decision-state changes:

```powershell
python -m pytest tests/test_monitor.py tests/test_monitor_state.py tests/test_dashboard_server.py tests/test_bot_gateway.py tests/test_decision_intelligence.py -q
```

## Full Local Gate

Run this before claiming broad branch health, after shared refactors, and before
handoff when time allows:

```powershell
python -m ruff check .
python -m pytest -q
Push-Location dashboard
npm test -- --run
npm run build
Pop-Location
git diff --check
```

## Staged Snapshot Gate

Use this when the worktree has unrelated WIP. It checks only files currently in
the git index, so the result is valid evidence for the next commit.

This checkout-index recipe is for targeted checkpoint checks. Do not use it for
the full Python suite because `tests/test_posix_launchers.py` needs `.git`
metadata to inspect launcher executable modes. Use the clean HEAD worktree gate
for full branch health.

```powershell
$ErrorActionPreference = 'Stop'
$repo = (Get-Location).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ('tgcs-staged-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
  git checkout-index -a -f --prefix="$temp\"
  Push-Location $temp
  python -m ruff check tests/test_contract_fixtures.py
  python -m pytest tests/test_contract_fixtures.py -q
  Pop-Location
  $nodeModules = Join-Path $repo 'dashboard\node_modules'
  if (Test-Path $nodeModules) {
    New-Item -ItemType Junction -Path (Join-Path $temp 'dashboard\node_modules') -Target $nodeModules | Out-Null
  }
  Push-Location (Join-Path $temp 'dashboard')
  npm test -- --run contract-privacy-fixtures
  Pop-Location
} finally {
  while ((Get-Location).Path -ne $repo) { Pop-Location }
  $junction = Join-Path $temp 'dashboard\node_modules'
  if (Test-Path $junction) { Remove-Item -LiteralPath $junction -Force }
  if ($temp.StartsWith([System.IO.Path]::GetTempPath())) {
    Remove-Item -LiteralPath $temp -Recurse -Force
  }
}
```

Replace the example paths and Vitest pattern with the targeted commands that
match the staged files. Record that scope in the commit note or iteration log.

## Clean HEAD Worktree Gate

Use this for full branch health while the main worktree is dirty. It checks a
detached worktree at `HEAD`, so git metadata is available and unrelated WIP is
excluded.

```powershell
$ErrorActionPreference = 'Stop'
$repo = (Get-Location).Path
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('tgcs-worktree-' + [guid]::NewGuid().ToString('N'))
try {
  git worktree add --detach $tempRoot HEAD
  Push-Location $tempRoot
  python -m ruff check .
  python -m pytest -q
  Pop-Location
  $nodeModules = Join-Path $repo 'dashboard\node_modules'
  if (Test-Path $nodeModules) {
    New-Item -ItemType Junction -Path (Join-Path $tempRoot 'dashboard\node_modules') -Target $nodeModules | Out-Null
  }
  Push-Location (Join-Path $tempRoot 'dashboard')
  npm test -- --run
  npm run build
  Pop-Location
} finally {
  while ((Get-Location).Path -ne $repo) { Pop-Location }
  $junction = Join-Path $tempRoot 'dashboard\node_modules'
  if (Test-Path $junction) { Remove-Item -LiteralPath $junction -Force }
  if (Test-Path $tempRoot) {
    git worktree remove --force $tempRoot
  }
}
```

## Extra Gates

- Dashboard layout or responsive CSS: run
  `python tools/quality_visual_audit.py <output-dir>`.
- Launcher or shell-script changes: run the matching CI syntax and line-ending
  checks for the touched platform.
- HTTP mutation or desktop action changes: include loopback, content-type, and
  fixed-argv negative tests.
- New JSON contract or payload field changes: add or update fixtures under
  `tests/fixtures/contracts/` and cover both Python producers and TypeScript
  consumers where both exist.

## Limits

These gates do not prove live Telegram availability, live LLM/provider behavior,
or human acceptance of product semantics. Treat those as separate operator
checks.
