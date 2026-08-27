from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class OCRJob(Base):
    __tablename__ = "ocr_jobs"

    id: Mapped[str] = mapped_column(
        primary_key=True,
    )

    filename: Mapped[str]

    document_type: Mapped[str]

    status: Mapped[str]

    pages: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    processing_time_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    gpu_name: Mapped[str | None] = mapped_column(
        nullable=True,
    )

    gpu_vram_total_gb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    gpu_peak_allocated_gb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    markdown: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    upload_path: Mapped[str | None] = mapped_column(
        nullable=True,
    )

    output_path: Mapped[str | None] = mapped_column(
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
