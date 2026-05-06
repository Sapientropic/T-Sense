#!/usr/bin/env bash
# Thin Unix wrapper for the cross-platform Python scanner.
# Usage: ./scan.sh <channel_list.txt> [hours] [scan.py options]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$#" -lt 1 ]; then
    echo "Usage: scan.sh <channel_list.txt> [hours] [scan.py options]" >&2
    exit 1
fi

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Error: .venv not found. Run setup.sh first." >&2
    exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate" 2>/dev/null || source "$SCRIPT_DIR/.venv/Scripts/activate" 2>/dev/null || true
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "Error: venv not activated. Run setup.sh first." >&2
    exit 1
fi

if ! command -v tg &>/dev/null; then
    echo "Error: tg command not found in venv. Run setup.sh first." >&2
    exit 1
fi

cd "$SCRIPT_DIR"
python scripts/scan.py "$@"
