import asyncio
import csv
import io
import json
import os
import re
import shutil
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Dict, List

import aiofiles
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import JOB_TTL, MAX_FILE_SIZE, MAX_FILES, TMP_DIR

app = FastAPI(title="PDF Metadata Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store (no Redis required) ───────────────────────────────────

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=4)

SAFE_NAME_RE = re.compile(r"[^\w\s.\-]")


def _safe_filename(name: str) -> str:
    name = os.path.basename(name)
    name = SAFE_NAME_RE.sub("_", name)
    return name[:200] or "file.pdf"


def _get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return job


def _cleanup_old_jobs() -> None:
    cutoff = time.time() - JOB_TTL
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j.get("created_at", 0) < cutoff]
        for jid in stale:
            _jobs.pop(jid, None)
            job_dir = os.path.join(TMP_DIR, jid)
            shutil.rmtree(job_dir, ignore_errors=True)


def _run_extraction(job_id: str, file_name: str, pdf_path: str) -> None:
    """Run in a thread-pool worker. Updates the in-memory job state when done."""
    from app.extraction.heuristics import extract_metadata

    try:
        result = extract_metadata(pdf_path, file_name)
    except Exception as exc:
        result = {
            "file_name": file_name,
            "title": None, "author": None, "publisher": None,
            "isbn": None, "copyright_holder": "unknown",
            "confidence": 0.0, "needs_review": True,
            "llm_used": False, "evidence": {}, "error": str(exc),
        }

    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["results"].append(result)
            job["processed_files"] += 1
            if job["processed_files"] >= job["total_files"]:
                job["status"] = "done"
                # Clean up temp files
                shutil.rmtree(os.path.join(TMP_DIR, job_id), ignore_errors=True)


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.post("/extract", status_code=202)
async def create_extract_job(files: List[UploadFile] = File(...)):
    _cleanup_old_jobs()

    if not files:
        raise HTTPException(400, "No files provided")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed per request")

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(TMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    saved: List[tuple] = []

    for upload in files:
        if not (upload.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, f"'{upload.filename}' is not a PDF file")

        safe_name = _safe_filename(upload.filename or "file.pdf")
        dest = os.path.join(job_dir, safe_name)
        if os.path.exists(dest):
            base, ext = os.path.splitext(safe_name)
            safe_name = f"{base}_{len(saved)}{ext}"
            dest = os.path.join(job_dir, safe_name)

        # Stream to disk in 1 MB chunks — avoids loading large PDFs into RAM
        size = 0
        CHUNK = 1024 * 1024  # 1 MB
        async with aiofiles.open(dest, "wb") as fp:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    await fp.aclose()
                    os.remove(dest)
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(
                        400,
                        f"'{upload.filename}' exceeds the "
                        f"{MAX_FILE_SIZE // (1024 * 1024)} MB size limit",
                    )
                await fp.write(chunk)

        saved.append((safe_name, dest))

    # Create job state
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "total_files": len(saved),
            "processed_files": 0,
            "results": [],
            "created_at": time.time(),
        }

    # Submit extraction tasks to thread pool
    loop = asyncio.get_event_loop()
    for name, path in saved:
        loop.run_in_executor(_executor, _run_extraction, job_id, name, path)

    return {"job_id": job_id}


@app.get("/extract/{job_id}/status")
def get_status(job_id: str):
    job = _get_job(job_id)
    return {
        "status": job["status"],
        "total_files": job["total_files"],
        "processed_files": job["processed_files"],
    }


@app.get("/extract/{job_id}/results")
def get_results(job_id: str):
    job = _get_job(job_id)
    return {
        "status": job["status"],
        "results": job.get("results", []),
    }


@app.get("/extract/{job_id}/export")
def export_results(job_id: str, format: str = Query("csv", pattern="^(csv|json)$")):
    job = _get_job(job_id)
    results = job.get("results", [])

    if format == "json":
        content = json.dumps(results, indent=2, ensure_ascii=False)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="results_{job_id[:8]}.json"'
            },
        )

    output = io.StringIO()
    fieldnames = [
        "file_name", "title", "author", "publisher", "isbn",
        "copyright_holder", "confidence", "llm_used", "needs_review", "error",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in results:
        flat = dict(row)
        flat["llm_used"] = "yes" if flat.get("llm_used") else "no"
        flat["needs_review"] = "yes" if flat.get("needs_review") else "no"
        writer.writerow(flat)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="results_{job_id[:8]}.csv"'
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api-status")
def api_status():
    """Diagnostic: check if OpenAI key is loaded and valid."""
    import os
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return {"key_loaded": False, "error": "OPENAI_API_KEY not set"}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        client.models.list()
        return {"key_loaded": True, "key_prefix": key[:12] + "...", "error": None}
    except Exception as e:
        return {"key_loaded": True, "key_prefix": key[:12] + "...", "error": str(e)}


# ── Serve the static frontend (must come last) ────────────────────────────────

def _find_frontend_dir() -> str:
    """Locate the bundled frontend/out dir whether running frozen or from source."""
    if getattr(sys, "frozen", False):
        # PyInstaller extracts data to sys._MEIPASS
        return os.path.join(sys._MEIPASS, "frontend_out")  # type: ignore[attr-defined]
    # Running from source: backend/app/main.py → backend/ → project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "frontend", "out")


_frontend_dir = _find_frontend_dir()
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
