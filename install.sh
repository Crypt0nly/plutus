#!/bin/bash
# Plutus Installer for macOS / Linux
# Usage: curl -sSL https://useplutus.ai/install.sh | sh
#
# What this script does:
#   1. Checks that Python 3.11+ is available
#   2. Installs Plutus via pip
#   3. Creates a launcher shortcut (macOS .app / Linux .desktop)
#   4. Launches Plutus in the background and opens the browser
#
# WSL is NOT installed by this script — it's a Windows-only feature.

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

OS="$(uname -s)"

# ── Step 1: Check Python ──────────────────────────────────

PYTHON_CMD=""

check_python() {
    local cmd=$1
    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | sed -n 's/Python \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
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
PYTHON_FULL_PATH=$(command -v "$PYTHON_CMD")
echo "[1/4] $PY_VER found."

# ── Step 2: Install Plutus ────────────────────────────────

echo "[2/4] Installing Plutus..."

$PYTHON_CMD -m pip install --upgrade pip >/dev/null 2>&1 || true
$PYTHON_CMD -m pip install --upgrade plutus-ai

echo "       Plutus installed."

# ── Step 3: Create Launcher & Shortcut ────────────────────

echo "[3/4] Creating launcher..."

PLUTUS_DIR="$HOME/.plutus"
mkdir -p "$PLUTUS_DIR"

# Create shared launcher script used by shortcuts
LAUNCHER="$PLUTUS_DIR/start.sh"
cat > "$LAUNCHER" << LAUNCHER_EOF
#!/bin/bash
# Plutus Launcher — double-click or run to start Plutus

PYTHON="$PYTHON_FULL_PATH"

# Check if Plutus is already running
if curl -sf http://localhost:7777/api/config > /dev/null 2>&1; then
    # Already running — just open the browser
    if [ "\$(uname -s)" = "Darwin" ]; then
        open "http://localhost:7777"
    else
        xdg-open "http://localhost:7777" 2>/dev/null || sensible-browser "http://localhost:7777" 2>/dev/null || true
    fi
else
    # Start Plutus in the background
    nohup "\$PYTHON" -m plutus start > "\$HOME/.plutus/plutus.log" 2>&1 &
    disown 2>/dev/null || true
fi
LAUNCHER_EOF
chmod +x "$LAUNCHER"

SHORTCUT_CREATED=false

if [ "$OS" = "Darwin" ]; then
    # ── macOS: Create a .app bundle ──
    APP_DIR="$HOME/Applications/Plutus.app"
    MACOS_DIR="$APP_DIR/Contents/MacOS"
    mkdir -p "$MACOS_DIR"

    # Info.plist
    cat > "$APP_DIR/Contents/Info.plist" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>plutus-launcher</string>
    <key>CFBundleIdentifier</key>
    <string>ai.plutus.app</string>
    <key>CFBundleName</key>
    <string>Plutus</string>
    <key>CFBundleDisplayName</key>
    <string>Plutus</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSBackgroundOnly</key>
    <true/>
</dict>
</plist>
PLIST_EOF

    # Executable
    cat > "$MACOS_DIR/plutus-launcher" << EXEC_EOF
#!/bin/bash
exec "$LAUNCHER"
EXEC_EOF
    chmod +x "$MACOS_DIR/plutus-launcher"

    SHORTCUT_CREATED=true
    echo "       App created at ~/Applications/Plutus.app"
    echo "       Tip: Drag it to your Dock for quick access."

else
    # ── Linux: Create a .desktop file ──
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_DIR/plutus.desktop" << DESKTOP_EOF
[Desktop Entry]
Name=Plutus
Comment=Autonomous AI Agent
Exec=bash "$LAUNCHER"
Terminal=false
Type=Application
Categories=Utility;Development;
StartupNotify=false
DESKTOP_EOF
    chmod +x "$DESKTOP_DIR/plutus.desktop"

    # Also place on the user's Desktop if the directory exists
    XDG_DESKTOP=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
    if [ -d "$XDG_DESKTOP" ]; then
        cp "$DESKTOP_DIR/plutus.desktop" "$XDG_DESKTOP/plutus.desktop"
        # Mark as trusted on GNOME so it's clickable without a warning
        gio set "$XDG_DESKTOP/plutus.desktop" metadata::trusted true 2>/dev/null || true
        chmod +x "$XDG_DESKTOP/plutus.desktop"
    fi

    SHORTCUT_CREATED=true
    echo "       App shortcut created."
    echo "       Search 'Plutus' in your app launcher to start it."
fi

# ── Step 4: Launch ────────────────────────────────────────

echo "[4/4] Launching Plutus..."
echo ""
echo "  ─────────────────────────────"
echo ""
echo "  Plutus is starting in the background..."
echo "  Your browser will open to http://localhost:7777"
echo "  First time? The setup wizard will guide you through everything."
echo ""

if [ "$SHORTCUT_CREATED" = true ]; then
    echo "  To start Plutus anytime:"
    if [ "$OS" = "Darwin" ]; then
        echo "    - Open 'Plutus' from ~/Applications or Spotlight"
        echo "    - Or drag it to your Dock for one-click access"
    else
        echo "    - Search 'Plutus' in your app launcher"
        echo "    - Or double-click 'Plutus' on your Desktop"
    fi
else
    echo "  To start Plutus anytime, run:"
    echo "    plutus start"
fi

echo ""
echo "  To stop: plutus stop (or close the terminal)"
echo "  ─────────────────────────────"
echo ""

# Launch via the launcher script
bash "$LAUNCHER"
