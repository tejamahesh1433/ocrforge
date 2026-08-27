import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

FRONTEND_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")


app = FastAPI(
    title="OCRForge API",
    description="Self-hosted GPU OCR and document parsing API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in FRONTEND_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


init_db()
ocr_service = OCRService()


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
        "completed_at": (
            job.completed_at.isoformat()
            if job.completed_at
            else None
        ),
        "document_url": f"/api/jobs/{job.id}/document",
    }

    if include_markdown:
        data["markdown"] = job.markdown

    return data


@app.get("/")
def root():
    return {
        "name": "OCRForge",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ocrforge",
        "version": "1.0.0",
        "database": "connected",
        "gpu": ocr_service.gpu_stats(),
    }


@app.post("/api/ocr")
async def run_ocr(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "upload").name

    extension = Path(filename).suffix.lower()

    allowed_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".pdf",
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Supported formats: PNG, JPG, JPEG and PDF",
        )

    job_id = str(uuid.uuid4())

    upload_path = UPLOAD_DIR / f"{job_id}{extension}"
    output_path = OUTPUT_DIR / job_id

    size = 0

    try:
        with upload_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_UPLOAD_BYTES:
                    buffer.close()
                    upload_path.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Maximum upload size is "
                            f"{MAX_UPLOAD_MB} MB"
                        ),
                    )

                buffer.write(chunk)

    finally:
        await file.close()

    document_type = (
        "pdf"
        if extension == ".pdf"
        else "image"
    )

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
        if extension == ".pdf":
            result = ocr_service.process_pdf(
                upload_path,
                output_path,
            )
        else:
            result = ocr_service.process_image(
                upload_path,
                output_path,
            )

        job.status = "completed"
        job.pages = result["pages"]
        job.processing_time_seconds = result[
            "processing_time_seconds"
        ]

        job.gpu_name = result["gpu"]["name"]
        job.gpu_vram_total_gb = result["gpu"][
            "vram_total_gb"
        ]
        job.gpu_peak_allocated_gb = result["gpu"][
            "vram_peak_allocated_gb"
        ]

        job.markdown = result["markdown"]
        job.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(job)

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = datetime.utcnow()

        db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    response = serialize_job(
        job,
        include_markdown=True,
    )

    response["gpu"].update({
        "available": result["gpu"]["available"],
        "vram_allocated_gb": result["gpu"][
            "vram_allocated_gb"
        ],
        "vram_reserved_gb": result["gpu"][
            "vram_reserved_gb"
        ],
    })

    return response


@app.get("/api/jobs")
def list_jobs(
    search: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(OCRJob)

    if search:
        search_term = f"%{search}%"

        query = query.filter(
            or_(
                OCRJob.filename.ilike(search_term),
                OCRJob.markdown.ilike(search_term),
            )
        )

    if status:
        query = query.filter(
            OCRJob.status == status
        )

    if document_type:
        query = query.filter(
            OCRJob.document_type == document_type
        )

    jobs = (
        query
        .order_by(desc(OCRJob.created_at))
        .limit(limit)
        .all()
    )

    return {
        "count": len(jobs),
        "jobs": [
            serialize_job(job)
            for job in jobs
        ],
    }


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.get(OCRJob, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="OCR job not found",
        )

    return serialize_job(
        job,
        include_markdown=True,
    )


@app.get("/api/jobs/{job_id}/document")
def get_document(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.get(OCRJob, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="OCR job not found",
        )

    if not job.upload_path:
        raise HTTPException(
            status_code=404,
            detail="Stored document not found",
        )

    path = Path(job.upload_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Stored document no longer exists",
        )

    return FileResponse(
        path=path,
        filename=job.filename,
    )


@app.get("/api/jobs/{job_id}/download/{format_name}")
def download_result(
    job_id: str,
    format_name: str,
    db: Session = Depends(get_db),
):
    job = db.get(OCRJob, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="OCR job not found",
        )

    if not job.markdown:
        raise HTTPException(
            status_code=404,
            detail="OCR result not available",
        )

    base_name = Path(job.filename).stem

    if format_name == "md":
        content = job.markdown
        suffix = ".md"
        media_type = "text/markdown"

    elif format_name == "txt":
        content = (
            job.markdown
            .replace("<PAGE>", "")
            .replace("</PAGE>", "")
        )
        suffix = ".txt"
        media_type = "text/plain"

    else:
        raise HTTPException(
            status_code=400,
            detail="Supported downloads: md, txt",
        )

    download_path = (
        Path(job.output_path)
        / f"{base_name}-ocr{suffix}"
    )

    download_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    download_path.write_text(
        content,
        encoding="utf-8",
    )

    return FileResponse(
        path=download_path,
        filename=download_path.name,
        media_type=media_type,
    )


@app.delete("/api/jobs/{job_id}")
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.get(OCRJob, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="OCR job not found",
        )

    if job.upload_path:
        Path(job.upload_path).unlink(
            missing_ok=True
        )

    if job.output_path:
        output_path = Path(job.output_path)

        if output_path.exists():
            shutil.rmtree(
                output_path,
                ignore_errors=True,
            )

    db.delete(job)
    db.commit()

    return {
        "status": "deleted",
        "job_id": job_id,
    }
