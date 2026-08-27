import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.services.ocr_service import OCRService


BASE_DIR = Path(__file__).resolve().parents[2]

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="OCRForge API",
    description="Self-hosted OCR and document parsing API",
    version="0.3.0",
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


ocr_service = OCRService()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ocrforge",
        "version": "0.3.0",
        "gpu": ocr_service.gpu_stats(),
    }


@app.post("/api/ocr")
async def run_ocr(file: UploadFile = File(...)):
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

    try:
        if extension == ".pdf":
            result = ocr_service.process_pdf(
                upload_path,
                output_path,
            )
            document_type = "pdf"

        else:
            result = ocr_service.process_image(
                upload_path,
                output_path,
            )
            document_type = "image"

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return {
        "job_id": job_id,
        "filename": filename,
        "document_type": document_type,
        "status": "completed",
        "pages": result["pages"],
        "processing_time_seconds": result["processing_time_seconds"],
        "file_size_bytes": file_size_bytes,
        "gpu": result["gpu"],
        "markdown": result["markdown"],
    }
