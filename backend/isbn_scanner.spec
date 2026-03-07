# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ISBN Scanner desktop app.
Run from the backend/ directory:
    pyinstaller isbn_scanner.spec
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Include baked key JSON if it exists at build time
_baked_json = [("app/_baked_keys.json", "app")] if os.path.exists("app/_baked_keys.json") else []

block_cipher = None

# Collect binaries/data/hiddenimports for packages with native extensions
fitz_datas, fitz_binaries, fitz_hidden = collect_all("fitz")
pdfplumber_datas, pdfplumber_binaries, pdfplumber_hidden = collect_all("pdfplumber")
pdfminer_datas, pdfminer_binaries, pdfminer_hidden = collect_all("pdfminer")
httpx_datas, httpx_binaries, httpx_hidden = collect_all("httpx")
openai_datas, openai_binaries, openai_hidden = collect_all("openai")
certifi_datas = collect_data_files("certifi")

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=fitz_binaries + pdfplumber_binaries + pdfminer_binaries + httpx_binaries + openai_binaries,
    datas=(
        fitz_datas
        + pdfplumber_datas
        + pdfminer_datas
        + httpx_datas
        + openai_datas
        + certifi_datas
        # Baked API key (JSON — reliable plain file I/O in frozen exe)
        + _baked_json
        # Our app source (.py files only — skip __pycache__ to avoid stale .pyc conflicts)
        + [("app/*.py", "app")]
        + [("app/extraction/*.py", "app/extraction")]
        # Static frontend (built by: cd ../frontend && npm run build)
        + [("../frontend/out", "frontend_out")]
    ),
    hiddenimports=(
        fitz_hidden
        + pdfplumber_hidden
        + pdfminer_hidden
        + httpx_hidden
        + openai_hidden
        + [
            # app modules
            "app.main",
            "app.config",
            "app._baked_keys",
            "app.extraction.heuristics",
            "app.extraction.vision_fallback",
            "app.extraction.llm_fallback",
            "app.extraction.layout",
            "app.extraction.isbn_validator",
            # uvicorn internals
            "uvicorn",
            "uvicorn.logging",
            "uvicorn.loops",
            "uvicorn.loops.auto",
            "uvicorn.loops.asyncio",
            "uvicorn.protocols",
            "uvicorn.protocols.http",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.http.h11_impl",
            "uvicorn.protocols.websockets",
            "uvicorn.protocols.websockets.auto",
            "uvicorn.lifespan",
            "uvicorn.lifespan.on",
            # fastapi / starlette
            "fastapi",
            "fastapi.staticfiles",
            "starlette",
            "starlette.staticfiles",
            "starlette.responses",
            # pydantic
            "pydantic",
            "pydantic.deprecated.class_validators",
            # other
            "aiofiles",
            "multipart",
            "python_multipart",
            "h11",
            "anyio",
            "anyio._backends._asyncio",
            "sniffio",
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["celery", "redis", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep console so server logs are visible
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ISBNScanner",
)
