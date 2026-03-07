import os
import tempfile

JOB_TTL = int(os.getenv("JOB_TTL", 3600))  # 1 hour
MAX_PAGES = int(os.getenv("MAX_PAGES", 5))
MAX_FILES = 50
MAX_FILE_SIZE = 300 * 1024 * 1024  # 300MB
TMP_DIR = os.path.join(tempfile.gettempdir(), "pdf_jobs")

# OpenAI key: env var wins; falls back to key baked in at build time
try:
    from app._baked_keys import OPENAI_API_KEY as _BAKED_KEY  # type: ignore
except ImportError:
    _BAKED_KEY = ""

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or _BAKED_KEY
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
