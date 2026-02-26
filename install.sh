#!/bin/bash
# Plutus Installer for macOS / Linux
# Usage: curl -sSL https://useplutus.ai/install.sh | sh
#
# What this script does:
#   1. Checks that Python 3.11+ is available
#   2. Installs Plutus via pip
#   3. Launches Plutus

set -e

echo ""
echo "  ____  _       _             "
echo " |  _ \| |_   _| |_ _   _ ___ "
echo " | |_) | | | | | __| | | / __|"
echo " |  __/| | |_| | |_| |_| \__ \\"
echo " |_|   |_|\__,_|\__|\__,_|___/"
echo ""
echo "  Plutus Installer"
echo "  ─────────────────────────────"
echo ""

# ── Step 1: Check Python ──────────────────────────────────

PYTHON_CMD=""

check_python() {
    local cmd=$1
    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            return 0
        fi
    fi
    return 1
}

if check_python python3; then
    true
elif check_python python; then
    true
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.11+ is required but not found."
    echo ""
    echo "  Install Python first:"
    echo "    macOS:  brew install python@3.11"
    echo "    Ubuntu: sudo apt install python3.11"
    echo "    Fedora: sudo dnf install python3.11"
    echo ""
    exit 1
fi

PY_VER=$($PYTHON_CMD --version 2>&1)
echo "[1/3] $PY_VER found."

# ── Step 2: Install Plutus ────────────────────────────────

echo "[2/3] Installing Plutus..."

$PYTHON_CMD -m pip install --upgrade pip >/dev/null 2>&1 || true
$PYTHON_CMD -m pip install plutus

echo "       Plutus installed."

# ── Step 3: Launch ────────────────────────────────────────

echo "[3/3] Launching Plutus..."
echo ""
echo "  ─────────────────────────────"
echo "  Plutus will open in your browser at http://localhost:7777"
echo "  First time? The setup wizard will guide you through everything."
echo "  ─────────────────────────────"
echo ""

plutus start
