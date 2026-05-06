#!/usr/bin/env bash
# Install tg-channel-scanner dependencies
# Requires: Python 3.12+

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TG Channel Scanner Setup ==="

# Check Python version
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 12 ]) || [ "$MAJOR" -gt 3 ]; then
            PYTHON="$cmd"
            echo "Found Python $VER ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3.12+ required. Install from https://python.org"
    exit 1
fi

# Create venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv .venv
fi

# Activate and verify
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "Error: Failed to activate virtual environment."
    exit 1
fi

# Install dependencies
echo "Installing pinned core dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "Installing optional pinned LLM dependencies (openai for summarize.py)..."
pip install -r requirements-llm.txt --quiet 2>/dev/null || echo "  (openai not installed — summarize.py will need it later)"

EXPECTED_TG_VERSION="0.9.0"
TG_VERSION="$(tg --version 2>/dev/null || true)"
if [ "$TG_VERSION" != "$EXPECTED_TG_VERSION" ]; then
    echo "Error: expected tgcli $EXPECTED_TG_VERSION, got '${TG_VERSION:-not found}'." >&2
    echo "Check requirements.txt before continuing." >&2
    exit 1
fi

# Configure tgcli (writes to global config at ~/.config/tgcli/)
TGCLI_CONFIG_DIR="$HOME/.config/tgcli"
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
    echo "2. Login to Telegram:"
    echo "   source .venv/bin/activate"
    echo "   tg auth login"
    echo ""
    echo "3. Run a scan:"
    echo "   ./scripts/scan.sh channel_lists/example.txt"
else
    echo "tgcli config already exists at $TGCLI_CONFIG — skipping."
    echo "To reconfigure, edit: $TGCLI_CONFIG"
fi

# Make scripts executable (macOS/Linux)
chmod +x scripts/scan.sh 2>/dev/null || true

# Create output dir
mkdir -p output

echo ""
echo "Setup complete. Next: edit config and run 'tg auth login'"
echo "  Config:  $TGCLI_CONFIG"
echo "  Verify:  source .venv/bin/activate && tg auth status"
