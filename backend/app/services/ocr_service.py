import tempfile
import threading
import time
from pathlib import Path

import fitz
import torch
from transformers import AutoModel, AutoTokenizer


class OCRService:
    def __init__(self):
        self.model_name = "baidu/Unlimited-OCR"
        self._inference_lock = threading.Lock()

        print("Loading Unlimited-OCR tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )

        print("Loading Unlimited-OCR model...")
        self.model = AutoModel.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            use_safetensors=True,
            torch_dtype=torch.bfloat16,
        )

        self.model = self.model.eval().cuda()

        print("Unlimited-OCR ready")
        print("GPU:", torch.cuda.get_device_name(0))
        print(
            "VRAM allocated:",
            round(torch.cuda.memory_allocated() / 1024**3, 2),
            "GB",
        )

    def gpu_stats(self) -> dict:
        if not torch.cuda.is_available():
            return {
                "available": False,
                "name": None,
                "vram_total_gb": 0,
                "vram_allocated_gb": 0,
                "vram_reserved_gb": 0,
                "vram_peak_allocated_gb": 0,
            }

        props = torch.cuda.get_device_properties(0)

        return {
            "available": True,
            "name": torch.cuda.get_device_name(0),
            "vram_total_gb": round(props.total_memory / 1024**3, 2),
            "vram_allocated_gb": round(
                torch.cuda.memory_allocated() / 1024**3,
                2,
            ),
            "vram_reserved_gb": round(
                torch.cuda.memory_reserved() / 1024**3,
                2,
            ),
            "vram_peak_allocated_gb": round(
                torch.cuda.max_memory_allocated() / 1024**3,
                2,
            ),
        }

    def process_image(self, image_path: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)

        with self._inference_lock:
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()

            self.model.infer(
                self.tokenizer,
                prompt="<image>document parsing.",
                image_file=str(image_path),
                output_path=str(output_dir),
                base_size=1024,
                image_size=640,
                crop_mode=True,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=128,
                save_results=True,
            )

            processing_time = time.perf_counter() - started
            gpu = self.gpu_stats()

        return {
            "markdown": self._read_result(output_dir),
            "pages": 1,
            "processing_time_seconds": round(processing_time, 2),
            "gpu": gpu,
        }

    def process_pdf(self, pdf_path: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ocrforge_pdf_") as temp_dir:
            image_paths = self._pdf_to_images(pdf_path, Path(temp_dir))

            print(f"PDF converted to {len(image_paths)} page(s)")
            print("Running multi-page OCR...")

            with self._inference_lock:
                torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()

                self.model.infer_multi(
                    self.tokenizer,
                    prompt="<image>Multi page parsing.",
                    image_files=image_paths,
                    output_path=str(output_dir),
                    image_size=1024,
                    max_length=32768,
                    no_repeat_ngram_size=35,
                    ngram_window=1024,
                    save_results=True,
                )

                processing_time = time.perf_counter() - started
                gpu = self.gpu_stats()

        return {
            "markdown": self._read_result(output_dir),
            "pages": len(image_paths),
            "processing_time_seconds": round(processing_time, 2),
            "gpu": gpu,
        }

    @staticmethod
    def _pdf_to_images(pdf_path: Path, temp_dir: Path) -> list[str]:
        document = fitz.open(str(pdf_path))
        matrix = fitz.Matrix(300 / 72, 300 / 72)
        image_paths: list[str] = []

        try:
            for page_number, page in enumerate(document):
                output_file = temp_dir / f"page_{page_number + 1:04d}.png"
                pixmap = page.get_pixmap(matrix=matrix)
                pixmap.save(str(output_file))
                image_paths.append(str(output_file))
        finally:
            document.close()

        if not image_paths:
            raise RuntimeError("PDF contains no pages")

        return image_paths

    @staticmethod
    def _read_result(output_dir: Path) -> str:
        result_file = output_dir / "result.md"

        if not result_file.exists():
            raise RuntimeError("OCR completed but result.md was not created")

        return result_file.read_text(encoding="utf-8")
