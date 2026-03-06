#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_mac.sh  –  Build ISBNScanner.app for macOS (Apple Silicon + Intel)
#
# Prerequisites (install once):
#   brew install node python@3.11 gettext
#
# Usage:
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Output: backend/dist/ISBNScanner.app  (also zipped to ISBNScanner-Mac.zip)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Read OpenAI API key ────────────────────────────────────────────────────
if [ -f ".env" ]; then
    OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' .env | head -1 | cut -d '=' -f2-)"
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY not found in .env"
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

# ── 3. Prepare Python virtual environment ─────────────────────────────────────
echo "→ Setting up Python virtual environment..."
cd backend

if [ ! -d "build_venv" ]; then
    python3 -m venv build_venv
fi
source build_venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller delocate

# ── 4. Bake in the OpenAI API key ────────────────────────────────────────────
echo "→ Baking OpenAI API key into build..."
python3 -c "
import os
key = '''${OPENAI_API_KEY}'''
with open('app/_baked_keys.py', 'w') as f:
    f.write('# Auto-generated at build time — DO NOT COMMIT\n')
    f.write(f'OPENAI_API_KEY = \"{key}\"\n')
"

# ── 5. Run PyInstaller ────────────────────────────────────────────────────────
echo "→ Running PyInstaller (this may take a few minutes)..."
rm -rf build/
pyinstaller isbn_scanner_mac.spec --noconfirm

# ── 6. Fix dylib references with delocate ────────────────────────────────────
# delocate finds all non-system dylibs (including libintl.8.dylib from Homebrew
# Python), copies them into the .app bundle, and fixes @rpath references so the
# app runs on any Mac without Homebrew installed.
echo "→ Fixing dylib references with delocate..."
delocate-path "dist/ISBNScanner.app" --lib-path /opt/homebrew/lib --lib-path /usr/local/lib -v 2>&1 | tail -10
echo "✓ dylibs bundled and rpaths fixed"

# ── 7. Remove secret file ─────────────────────────────────────────────────────
rm -f app/_baked_keys.py
echo "✓ Secret file removed"

deactivate

# ── 8. Zip for distribution ───────────────────────────────────────────────────
echo "→ Creating zip..."
cd dist
zip -r --symlinks "$SCRIPT_DIR/ISBNScanner-Mac.zip" ISBNScanner.app/
cd ..

APP_SIZE=$(du -sh dist/ISBNScanner.app | cut -f1)
ZIP_SIZE=$(du -sh "$SCRIPT_DIR/ISBNScanner-Mac.zip" | cut -f1)

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Build complete!"
echo "  App:  backend/dist/ISBNScanner.app  ($APP_SIZE)"
echo "  Zip:  ISBNScanner-Mac.zip  ($ZIP_SIZE)  ← share this"
echo ""
echo "  Team instructions:"
echo "  1. Download & unzip ISBNScanner-Mac.zip"
echo "  2. Right-click ISBNScanner.app → Open → Open"
echo "     (one-time only — macOS security warning)"
echo "  3. Browser opens automatically at http://localhost:8000"
echo "  4. Right-click Dock icon → Quit to stop"
echo "════════════════════════════════════════════════════════"
