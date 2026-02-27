#!/bin/bash
# Build a compiled release wheel locally (for testing).
#
# Usage:
#   ./scripts/build_release.sh
#
# This does the same thing the CI does:
#   1. Build the React frontend
#   2. Compile protected modules with Cython
#   3. Strip .py source for compiled modules
#   4. Build the wheel
#
# The resulting wheel is in dist/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo "═══════════════════════════════════════════"
echo "  Plutus — Compiled Release Build"
echo "═══════════════════════════════════════════"
echo ""

# ── Step 1: Build UI ──────────────────────────
echo "[1/5] Building frontend..."
if [ -d "ui/node_modules" ]; then
    (cd ui && npm run build)
else
    (cd ui && npm ci && npm run build)
fi
echo "       Frontend built."
echo ""

# ── Step 2: Install build deps ───────────────
echo "[2/5] Installing build dependencies..."
pip install "cython>=3.0" "setuptools>=69.0" build
echo "       Build deps ready."
echo ""

# ── Step 3: Compile protected modules ────────
echo "[3/5] Compiling protected modules with Cython..."
python build_compiled.py build_ext --inplace
echo "       Compilation complete."
echo ""

# ── Step 4: Strip .py source ─────────────────
echo "[4/5] Stripping source files for compiled modules..."
python scripts/strip_sources.py --apply
echo ""

# ── Step 5: Build wheel ──────────────────────
echo "[5/5] Building wheel..."
python -m build --wheel
echo ""

echo "═══════════════════════════════════════════"
echo "  Build complete! Wheel is in dist/"
echo ""
ls -lh dist/*.whl 2>/dev/null || echo "  (no wheel found — check for errors above)"
echo ""
echo "  Test it with:"
echo "    pip install dist/plutus_ai-*.whl"
echo "    python -c 'from plutus.core.agent import AgentRuntime; print(\"OK\")'"
echo "═══════════════════════════════════════════"
