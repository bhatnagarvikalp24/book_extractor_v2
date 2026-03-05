import json
import os
import shutil
import time

import redis as redis_lib

from app.celery_app import celery
from app.config import JOB_TTL, TMP_DIR
from app.redis_client import redis_client


# ── helpers ──────────────────────────────────────────────────────────────────

def _atomic_update_job(job_id: str, file_result: dict) -> None:
    """Atomically append a file result to the job state using WATCH/MULTI/EXEC."""
    key = f"job:{job_id}"
    with redis_client.pipeline() as pipe:
        while True:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if not raw:
                    pipe.reset()
                    return
                job = json.loads(raw)

                # Transition queued -> running on first update
                if job.get("status") == "queued":
                    job["status"] = "running"

                job["results"].append(file_result)
                job["processed_files"] = len(job["results"])

                if file_result.get("error"):
                    job["errors"].append(
                        {"file": file_result["file_name"], "error": file_result["error"]}
                    )

                if job["processed_files"] >= job["total_files"]:
                    job["status"] = "done"

                pipe.multi()
                pipe.set(key, json.dumps(job), ex=JOB_TTL)
                pipe.execute()

                # Schedule file cleanup when job is done
                if job["status"] == "done":
                    cleanup_job_files.apply_async(args=[job_id], countdown=JOB_TTL)

                break
            except redis_lib.WatchError:
                continue  # retry


# ── main task ────────────────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=1, default_retry_delay=5)
def process_pdf(self, job_id: str, file_name: str, file_path: str, file_index: int) -> None:
    """Extract metadata from one PDF and write result into Redis job state."""
    try:
        from app.extraction.heuristics import extract_metadata

        result = extract_metadata(file_path, file_name)
    except Exception as exc:
        result = {
            "file_name": file_name,
            "title": None,
            "author": None,
            "publisher": None,
            "isbn": None,
            "copyright_holder": "unknown",
            "confidence": 0.0,
            "needs_review": True,
            "llm_used": False,
            "evidence": {},
            "error": str(exc),
        }

    _atomic_update_job(job_id, result)


# ── cleanup tasks ─────────────────────────────────────────────────────────────

@celery.task
def cleanup_job_files(job_id: str) -> None:
    """Delete temp files for a completed/expired job and remove Redis key."""
    job_dir = os.path.join(TMP_DIR, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=True)
    redis_client.delete(f"job:{job_id}")


@celery.task
def cleanup_stale_jobs() -> None:
    """
    Periodic beat task: remove temp dirs older than JOB_TTL seconds.
    Catches jobs whose cleanup task was never delivered.
    """
    if not os.path.exists(TMP_DIR):
        return
    now = time.time()
    for entry in os.scandir(TMP_DIR):
        if entry.is_dir():
            try:
                mtime = entry.stat().st_mtime
                if now - mtime > JOB_TTL:
                    shutil.rmtree(entry.path, ignore_errors=True)
                    # Best-effort Redis cleanup (key may already be expired)
                    redis_client.delete(f"job:{entry.name}")
            except OSError:
                pass
