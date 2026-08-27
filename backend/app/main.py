import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.init_db import init_db
from app.db.models import OCRJob
from app.services.ocr_service import OCRService

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

app = FastAPI(
    title="OCRForge API",
    description="Self-hosted GPU OCR and document parsing API",
    version="1.0.0",
)

origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
ocr_service = OCRService()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def serialize_job(job: OCRJob, include_markdown: bool = False):
    data = {
        "job_id": job.id,
        "filename": job.filename,
        "document_type": job.document_type,
        "status": job.status,
        "pages": job.pages,
        "processing_time_seconds": job.processing_time_seconds,
        "file_size_bytes": job.file_size_bytes,
        "gpu": {
            "name": job.gpu_name,
            "vram_total_gb": job.gpu_vram_total_gb,
            "vram_peak_allocated_gb": job.gpu_peak_allocated_gb,
        },
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "document_url": f"/api/jobs/{job.id}/document",
        "markdown_url": f"/api/jobs/{job.id}/export/md",
        "text_url": f"/api/jobs/{job.id}/export/txt",
    }
    if include_markdown:
        data["markdown"] = job.markdown
    return data


def require_job(db: Session, job_id: str) -> OCRJob:
    job = db.get(OCRJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="OCR job not found")
    return job


def plain_text(markdown: str | None) -> str:
    if not markdown:
        return ""
    return markdown.replace("<PAGE>", "").replace("</PAGE>", "")


@app.get("/")
def root():
    return {"service": "OCRForge API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ocrforge",
        "version": "1.0.0",
        "gpu": ocr_service.gpu_stats(),
    }


@app.post("/api/ocr")
async def run_ocr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = Path(file.filename or "upload").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported formats: PNG, JPG, JPEG and PDF")

    job_id = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}{extension}"
    output_path = OUTPUT_DIR / job_id

    size = 0
    try:
        with upload_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File is too large")
                buffer.write(chunk)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    document_type = "pdf" if extension == ".pdf" else "image"
    job = OCRJob(
        id=job_id,
        filename=filename,
        document_type=document_type,
        status="processing",
        file_size_bytes=size,
        upload_path=str(upload_path),
        output_path=str(output_path),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        result = (
            ocr_service.process_pdf(upload_path, output_path)
            if extension == ".pdf"
            else ocr_service.process_image(upload_path, output_path)
        )
        job.status = "completed"
        job.pages = result["pages"]
        job.processing_time_seconds = result["processing_time_seconds"]
        job.gpu_name = result["gpu"]["name"]
        job.gpu_vram_total_gb = result["gpu"]["vram_total_gb"]
        job.gpu_peak_allocated_gb = result["gpu"]["vram_peak_allocated_gb"]
        job.markdown = result["markdown"]
        job.completed_at = utcnow()
        db.commit()
        db.refresh(job)
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response = serialize_job(job, include_markdown=True)
    response["gpu"].update({
        "available": result["gpu"]["available"],
        "vram_allocated_gb": result["gpu"]["vram_allocated_gb"],
        "vram_reserved_gb": result["gpu"]["vram_reserved_gb"],
    })
    return response


@app.get("/api/jobs")
def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(OCRJob)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(OCRJob.filename.ilike(term), OCRJob.markdown.ilike(term)))
    if status:
        query = query.filter(OCRJob.status == status)
    if document_type:
        query = query.filter(OCRJob.document_type == document_type)

    total = query.count()
    jobs = query.order_by(desc(OCRJob.created_at)).offset(offset).limit(limit).all()
    return {"count": len(jobs), "total": total, "offset": offset, "limit": limit, "jobs": [serialize_job(job) for job in jobs]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return serialize_job(require_job(db, job_id), include_markdown=True)


@app.get("/api/jobs/{job_id}/document")
def get_document(job_id: str, db: Session = Depends(get_db)):
    job = require_job(db, job_id)
    if not job.upload_path:
        raise HTTPException(status_code=404, detail="Stored document not found")
    path = Path(job.upload_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored document not found")
    media_type = "application/pdf" if job.document_type == "pdf" else "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return FileResponse(path, media_type=media_type, filename=job.filename, content_disposition_type="inline")


@app.get("/api/jobs/{job_id}/export/md")
def export_markdown(job_id: str, db: Session = Depends(get_db)):
    job = require_job(db, job_id)
    name = f'{Path(job.filename).stem}-ocr.md'
    return PlainTextResponse(job.markdown or "", media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/jobs/{job_id}/export/txt")
def export_text(job_id: str, db: Session = Depends(get_db)):
    job = require_job(db, job_id)
    name = f'{Path(job.filename).stem}-ocr.txt'
    return PlainTextResponse(plain_text(job.markdown), media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = require_job(db, job_id)
    if job.upload_path:
        Path(job.upload_path).unlink(missing_ok=True)
    if job.output_path:
        shutil.rmtree(Path(job.output_path), ignore_errors=True)
    db.delete(job)
    db.commit()
    return {"status": "deleted", "job_id": job_id}
