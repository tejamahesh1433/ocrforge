import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc
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


app = FastAPI(
    title="OCRForge API",
    description="Self-hosted OCR and document parsing API",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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
            job.completed_at.isoformat() if job.completed_at else None
        ),
    }

    if include_markdown:
        data["markdown"] = job.markdown

    return data


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ocrforge",
        "version": "0.4.0",
        "gpu": ocr_service.gpu_stats(),
    }


@app.post("/api/ocr")
async def run_ocr(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = file.filename or "upload"

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

    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size_bytes = upload_path.stat().st_size

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
        file_size_bytes=file_size_bytes,
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
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))

    jobs = (
        db.query(OCRJob)
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

    upload_path = (
        Path(job.upload_path)
        if job.upload_path
        else None
    )

    output_path = (
        Path(job.output_path)
        if job.output_path
        else None
    )

    if upload_path and upload_path.exists():
        upload_path.unlink()

    if output_path and output_path.exists():
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
