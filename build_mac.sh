#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_mac.sh  –  Build the ISBN Scanner desktop app for macOS
#
# Prerequisites (run once):
#   brew install node python@3.11
#
# Usage:
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Output:  backend/dist/ISBNScanner/ISBNScanner   (double-click or run directly)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Read OpenAI API key ────────────────────────────────────────────────────
if [ -f ".env" ]; then
    OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' .env | head -1 | cut -d '=' -f2-)"
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY not found in .env file."
    echo "Create a .env file with: OPENAI_API_KEY=sk-proj-..."
    exit 1
fi

echo "✓ OpenAI API key loaded"

# ── 2. Build Next.js static frontend ─────────────────────────────────────────
echo "→ Building frontend..."
cd frontend
npm ci --prefer-offline --silent
npm run build
cd ..
echo "✓ Frontend built → frontend/out/"

# ── 3. Prepare Python environment ─────────────────────────────────────────────
echo "→ Setting up Python virtual environment..."
cd backend

if [ ! -d "build_venv" ]; then
    python3 -m venv build_venv
fi
source build_venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

# ── 4. Bake in the OpenAI API key ────────────────────────────────────────────
echo "→ Baking OpenAI API key into build..."
cat > app/_baked_keys.py << EOF
# Auto-generated at build time — DO NOT COMMIT
OPENAI_API_KEY = "${OPENAI_API_KEY}"
EOF

# ── 5. Run PyInstaller ────────────────────────────────────────────────────────
echo "→ Running PyInstaller (this may take a few minutes)..."
# Clean stale build cache to ensure fresh compile of app modules
rm -rf build/
pyinstaller isbn_scanner.spec --noconfirm

# ── 6. Clean up secret file ───────────────────────────────────────────────────
rm -f app/_baked_keys.py
echo "✓ Secret file removed"

deactivate

# ── 7. Done ───────────────────────────────────────────────────────────────────
DIST_PATH="$SCRIPT_DIR/backend/dist/ISBNScanner/ISBNScanner"
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Build complete!"
echo "  Executable: $DIST_PATH"
echo ""
echo "  To run:  $DIST_PATH"
echo "  Then open http://localhost:8000 in your browser"
echo "  (browser opens automatically)"
echo "════════════════════════════════════════════════════════"
