# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ISBN Scanner — macOS .app bundle.

Produces:  backend/dist/ISBNScanner.app
Run from backend/ directory:
    pyinstaller isbn_scanner_mac.spec --noconfirm

NOTE: After PyInstaller, build_mac.sh runs `delocate-path` to bundle any
remaining Homebrew dylibs (e.g. libintl.8.dylib from Homebrew Python) and
fix all @rpath / @loader_path references so the app is self-contained.
"""

import os
import subprocess
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── 1. Collect Homebrew dylibs that the Python runtime depends on ─────────────
# Homebrew Python links against libintl (gettext) which is not present on a
# stock Mac. We copy it into the bundle so the app is fully self-contained.

def _find_dylib(*names) -> list:
    """Search common Homebrew prefixes and return (src, '.') tuples."""
    search_dirs = [
        "/opt/homebrew/opt/gettext/lib",   # Apple Silicon
        "/opt/homebrew/lib",
        "/usr/local/opt/gettext/lib",       # Intel Homebrew
        "/usr/local/lib",
    ]
    result = []
    for name in names:
        for d in search_dirs:
            p = Path(d) / name
            if p.is_file():
                result.append((str(p), "."))
                break
    return result

extra_binaries = _find_dylib(
    "libintl.8.dylib",
    "libintl.dylib",
    "libiconv.2.dylib",
)

# ── 2. Collect package data / binaries / hidden imports ──────────────────────

fitz_datas, fitz_binaries, fitz_hidden = collect_all("fitz")
pdfplumber_datas, pdfplumber_binaries, pdfplumber_hidden = collect_all("pdfplumber")
pdfminer_datas, pdfminer_binaries, pdfminer_hidden = collect_all("pdfminer")
httpx_datas, httpx_binaries, httpx_hidden = collect_all("httpx")
openai_datas, openai_binaries, openai_hidden = collect_all("openai")
certifi_datas = collect_data_files("certifi")

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=(
        extra_binaries
        + fitz_binaries + pdfplumber_binaries + pdfminer_binaries
        + httpx_binaries + openai_binaries
    ),
    datas=(
        fitz_datas + pdfplumber_datas + pdfminer_datas
        + httpx_datas + openai_datas + certifi_datas
        + [("app/*.py", "app")]
        + [("app/extraction/*.py", "app/extraction")]
        + [("../frontend/out", "frontend_out")]
    ),
    hiddenimports=(
        fitz_hidden + pdfplumber_hidden + pdfminer_hidden
        + httpx_hidden + openai_hidden
        + [
            "app.main", "app.config", "app._baked_keys",
            "app.extraction.heuristics", "app.extraction.vision_fallback",
            "app.extraction.llm_fallback", "app.extraction.layout",
            "app.extraction.isbn_validator",
            "uvicorn", "uvicorn.logging",
            "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
            "uvicorn.protocols", "uvicorn.protocols.http",
            "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
            "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
            "uvicorn.lifespan", "uvicorn.lifespan.on",
            "fastapi", "fastapi.staticfiles",
            "starlette", "starlette.staticfiles", "starlette.responses",
            "pydantic", "pydantic.deprecated.class_validators",
            "aiofiles", "multipart", "python_multipart",
            "h11", "anyio", "anyio._backends._asyncio", "sniffio",
        ]
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=["celery", "redis", "tkinter"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ISBNScanner",
    debug=False,
    strip=False,
    upx=False,
    console=False,    # No terminal window
    windowed=True,    # Required for .app bundle
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ISBNScanner",
)

# ── 3. Wrap in a proper macOS .app bundle ────────────────────────────────────

app = BUNDLE(
    coll,
    name="ISBNScanner.app",
    icon=None,
    bundle_identifier="com.isbnscanner.desktop",
    info_plist={
        "CFBundleName": "ISBN Scanner",
        "CFBundleDisplayName": "ISBN Scanner",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabled": False,
        # LSUIElement=False → app appears in Dock so user can right-click → Quit
        "LSUIElement": False,
    },
)
