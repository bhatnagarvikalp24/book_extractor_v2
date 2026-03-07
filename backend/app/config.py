import os
import sys
import tempfile

JOB_TTL = int(os.getenv("JOB_TTL", 3600))  # 1 hour
MAX_PAGES = int(os.getenv("MAX_PAGES", 5))
MAX_FILES = 50
MAX_FILE_SIZE = 300 * 1024 * 1024  # 300MB
TMP_DIR = os.path.join(tempfile.gettempdir(), "pdf_jobs")

# OpenAI key loading — priority order:
# 1. Environment variable (already exported)
# 2. Baked JSON file — most reliable in frozen exe (plain file I/O, no import magic)
# 3. Baked Python module — fallback for non-frozen runs
# 4. .env file — local dev only

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 2. JSON file: present when built by PyInstaller (bundled via datas)
if not OPENAI_API_KEY:
    try:
        import json
        _meipass = getattr(sys, "_MEIPASS", None)
        if _meipass:
            _json_path = os.path.join(_meipass, "app", "_baked_keys.json")
            if os.path.exists(_json_path):
                with open(_json_path) as _f:
                    OPENAI_API_KEY = json.load(_f).get("OPENAI_API_KEY", "")
    except Exception:
        pass

# 3. Python module fallback
if not OPENAI_API_KEY:
    try:
        from app._baked_keys import OPENAI_API_KEY as _BAKED_KEY  # type: ignore
        OPENAI_API_KEY = _BAKED_KEY
    except Exception:
        pass

# 4. .env file (local dev)
if not OPENAI_API_KEY:
    try:
        import pathlib
        _env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
        for _line in _env_file.read_text().splitlines():
            if _line.startswith("OPENAI_API_KEY="):
                OPENAI_API_KEY = _line.split("=", 1)[1].strip()
                break
    except Exception:
        pass

if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
