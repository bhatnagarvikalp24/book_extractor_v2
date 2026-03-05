import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JOB_TTL = int(os.getenv("JOB_TTL", 3600))  # 1 hour
MAX_PAGES = int(os.getenv("MAX_PAGES", 5))
MAX_FILES = 50
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
TMP_DIR = "/tmp/pdf_jobs"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
