from celery import Celery
from app.config import REDIS_URL, JOB_TTL

celery = Celery(
    "pdf_extractor",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=JOB_TTL,
    beat_schedule={
        "cleanup-stale-jobs": {
            "task": "app.tasks.cleanup_stale_jobs",
            "schedule": 1800.0,  # every 30 minutes
        }
    },
)
