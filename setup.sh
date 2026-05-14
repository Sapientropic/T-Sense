#!/usr/bin/env bash
# Install T-Sense dependencies.
# Requires: Python 3.12+ (system, or via uv/pipx).
#
# If your system Python is older than 3.12, install uv first:
#   https://docs.astral.sh/uv/getting-started/installation/
# setup.sh will then use uv to provision a managed Python automatically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== T-Sense Setup ==="

SKIP_INSTALL="${TG_SCANNER_SETUP_SKIP_INSTALL:-0}"

# --- Find a suitable Python 3.12+ ---
# Skip Windows Store stubs (python3.exe that exits non-zero without printing a version).
find_python() {
    local cmd
    local ver
    local major
    local minor
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver="$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)" || continue
            major="$(echo "$ver" | cut -d. -f1)"
            minor="$(echo "$ver" | cut -d. -f2)"
            if { [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; } || [ "$major" -gt 3 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

is_wsl() {
    grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null
}

if [ "$SKIP_INSTALL" = "1" ]; then
    echo "Skipping dependency installation because TG_SCANNER_SETUP_SKIP_INSTALL=1."
else
    PYTHON=""
    USE_UV=false

    if PYTHON="$(find_python)"; then
        VER="$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
        echo "Found Python $VER ($PYTHON)"
    elif command -v uv >/dev/null 2>&1; then
        echo "System Python < 3.12. Using uv to provision a managed Python..."
        USE_UV=true
    else
        echo "Error: Python 3.12+ required." >&2
        echo "Install from https://python.org or install uv: https://docs.astral.sh/uv/" >&2
        exit 1
    fi

    # --- Create venv ---
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        if [ "$USE_UV" = true ]; then
            uv venv .venv --python 3.13
        else
            "$PYTHON" -m venv .venv
        fi
    fi

    # Activate and verify.
    # shellcheck disable=SC1091
    source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        echo "Error: Failed to activate virtual environment." >&2
        exit 1
    fi

    if [ -x ".venv/bin/python" ]; then
        VENV_PYTHON=".venv/bin/python"
    elif [ -x ".venv/Scripts/python.exe" ] && ! is_wsl; then
        # Windows venv Python cannot reliably open POSIX /mnt/... paths under WSL.
        VENV_PYTHON=".venv/Scripts/python.exe"
    else
        echo "Error: virtual environment Python not found." >&2
        exit 1
    fi

    if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
        echo "pip not found in venv; bootstrapping with ensurepip..."
        "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null
    fi

    # --- Install dependencies ---
    echo "Installing pinned core dependencies..."
    "$VENV_PYTHON" -m pip install --upgrade pip --quiet
    "$VENV_PYTHON" -m pip install -r requirements.txt --quiet

    echo "Installing optional pinned LLM dependencies (openai for summarize.py)..."
    "$VENV_PYTHON" -m pip install -r requirements-llm.txt --quiet 2>/dev/null || echo "  (openai not installed; summarize.py will need it later)"

    if [ -f requirements-desktop.txt ]; then
        echo "Installing optional desktop integration dependencies..."
        "$VENV_PYTHON" -m pip install -r requirements-desktop.txt --quiet 2>/dev/null || echo "  (desktop keyring extras not installed; environment variables still work)"
    fi

    TELETHON_VERSION="$("$VENV_PYTHON" -c "import telethon; print(telethon.__version__)" 2>/dev/null || true)"
    if [ -z "$TELETHON_VERSION" ]; then
        echo "Error: telethon not importable. Check requirements.txt and venv." >&2
        exit 1
    fi
    echo "telethon $TELETHON_VERSION OK"
fi

# --- Configure scanner (default path kept for backward compatibility) ---
TGCLI_CONFIG_DIR="${TG_SCANNER_CONFIG_DIR:-${TGCLI_CONFIG_DIR:-$HOME/.config/tgcli}}"
TGCLI_CONFIG="$TGCLI_CONFIG_DIR/config.toml"

if [ ! -f "$TGCLI_CONFIG" ]; then
    mkdir -p "$TGCLI_CONFIG_DIR"
    cp config.example.toml "$TGCLI_CONFIG"
    echo ""
    echo "=== Next Steps ==="
    echo "1. Edit Telegram API credentials:"
    echo "   $TGCLI_CONFIG"
    echo "   Get your api_id and api_hash from: https://my.telegram.org/apps"
    echo "   (If the form shows ERROR, see docs/getting-api-credentials.md)"
    echo ""
    echo "2. Check jobs prerequisites, log in, then run a dry monitor:"
    echo "   ./tgcs quickstart jobs"
    echo "   ./tgcs doctor --profile jobs"
    echo "   ./tgcs login"
    echo "   ./tgcs monitor run --profile-id jobs-fast --delivery-mode live"
else
    echo "Scanner config already exists at $TGCLI_CONFIG; skipping."
    echo "To reconfigure, edit: $TGCLI_CONFIG"
fi

# Make scripts executable (macOS/Linux).
chmod +x setup.sh tgcs signal-desk "Signal Desk.command" scripts/scan.sh 2>/dev/null || true

# Create output dir.
mkdir -p output

echo ""
echo "Initializing local project defaults (jobs starter)..."
if ./tgcs init --starter jobs; then
    echo "Local project defaults ready."
else
    echo "Warning: local project defaults were not initialized. Run ./tgcs init --starter jobs after setup."
fi

echo ""
echo "Setup complete. Next: edit config and run jobs-fast"
echo "  Config:  $TGCLI_CONFIG"
echo "  Next:    ./tgcs quickstart jobs"
echo "  Run:     ./tgcs doctor --profile jobs && ./tgcs login && ./tgcs monitor run --profile-id jobs-fast --delivery-mode live"
echo "  Schedule preview: ./tgcs schedule print --profile-id jobs-fast --interval-minutes 15"
