@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM build_windows.bat  –  Build the ISBN Scanner desktop app for Windows
REM
REM Prerequisites (install once):
REM   - Python 3.11+  from https://www.python.org/downloads/
REM   - Node.js 20+   from https://nodejs.org/
REM
REM Usage:  Double-click or run from Command Prompt
REM Output: backend\dist\ISBNScanner\ISBNScanner.exe
REM ─────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM ── 1. Read OpenAI API key from .env ─────────────────────────────────────────
set OPENAI_API_KEY=
for /f "tokens=1,* delims==" %%A in (.env) do (
    if "%%A"=="OPENAI_API_KEY" set OPENAI_API_KEY=%%B
)

if "%OPENAI_API_KEY%"=="" (
    echo ERROR: OPENAI_API_KEY not found in .env file.
    echo Create a .env file with: OPENAI_API_KEY=sk-proj-...
    pause
    exit /b 1
)

echo [OK] OpenAI API key loaded

REM ── 2. Build Next.js static frontend ─────────────────────────────────────────
echo [->] Building frontend...
cd frontend
call npm ci --prefer-offline --silent
call npm run build
cd ..
echo [OK] Frontend built

REM ── 3. Prepare Python virtual environment ────────────────────────────────────
echo [->] Setting up Python virtual environment...
cd backend

if not exist build_venv (
    python -m venv build_venv
)
call build_venv\Scripts\activate.bat

python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet pyinstaller

REM ── 4. Bake in the OpenAI API key ────────────────────────────────────────────
echo [->] Baking OpenAI API key into build...
(echo # Auto-generated at build time -- DO NOT COMMIT
echo OPENAI_API_KEY = "%OPENAI_API_KEY%") > app\_baked_keys.py

REM ── 5. Run PyInstaller ────────────────────────────────────────────────────────
echo [->] Running PyInstaller (this may take a few minutes)...
REM Clean stale build cache to ensure fresh compile of app modules
if exist build rmdir /s /q build
pyinstaller isbn_scanner.spec --noconfirm

REM ── 6. Clean up secret file ───────────────────────────────────────────────────
del /f app\_baked_keys.py
echo [OK] Secret file removed

call build_venv\Scripts\deactivate.bat

REM ── 7. Done ───────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Build complete!
echo   Executable: %CD%\dist\ISBNScanner\ISBNScanner.exe
echo.
echo   To run: double-click ISBNScanner.exe
echo   Browser opens automatically at http://localhost:8000
echo ============================================================

pause
