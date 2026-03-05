import csv
import io
import json
import os
import re
import uuid
from typing import List

import aiofiles
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import JOB_TTL, MAX_FILE_SIZE, MAX_FILES, TMP_DIR
from app.redis_client import redis_client
from app.tasks import process_pdf

app = FastAPI(title="PDF Metadata Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SAFE_NAME_RE = re.compile(r"[^\w\s.\-]")


def _safe_filename(name: str) -> str:
    name = os.path.basename(name)
    name = SAFE_NAME_RE.sub("_", name)
    return name[:200] or "file.pdf"


def _get_job(job_id: str) -> dict:
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return json.loads(raw)


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.post("/extract", status_code=202)
async def create_extract_job(files: List[UploadFile] = File(...)):
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

        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                400, f"'{upload.filename}' exceeds the 20 MB size limit"
            )

        safe_name = _safe_filename(upload.filename or "file.pdf")
        # Deduplicate filenames within the same job
        dest = os.path.join(job_dir, safe_name)
        if os.path.exists(dest):
            base, ext = os.path.splitext(safe_name)
            safe_name = f"{base}_{len(saved)}{ext}"
            dest = os.path.join(job_dir, safe_name)

        async with aiofiles.open(dest, "wb") as fp:
            await fp.write(content)
        saved.append((safe_name, dest))

    # Initialise Redis job state
    job_state = {
        "status": "queued",
        "total_files": len(saved),
        "processed_files": 0,
        "results": [],
        "errors": [],
    }
    redis_client.set(f"job:{job_id}", json.dumps(job_state), ex=JOB_TTL)

    # Enqueue one Celery task per file
    for idx, (name, path) in enumerate(saved):
        process_pdf.apply_async(args=[job_id, name, path, idx])

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
        "errors": job.get("errors", []),
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

    # CSV
    output = io.StringIO()
    fieldnames = [
        "file_name",
        "title",
        "author",
        "publisher",
        "isbn",
        "copyright_holder",
        "confidence",
        "llm_used",
        "needs_review",
        "error",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in results:
        # Flatten booleans for CSV readability
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
