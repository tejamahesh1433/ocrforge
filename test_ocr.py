import os
import torch
from transformers import AutoModel, AutoTokenizer

MODEL_NAME = "baidu/Unlimited-OCR"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
)

print("Loading model...")
model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    use_safetensors=True,
    torch_dtype=torch.bfloat16,
)

model = model.eval().cuda()

print("Model loaded successfully.")
print("GPU:", torch.cuda.get_device_name(0))
print(
    "Allocated VRAM GB:",
    round(torch.cuda.memory_allocated() / 1024**3, 2),
)

image_path = "uploads/test.png"
output_path = "outputs/test"

if not os.path.exists(image_path):
    raise FileNotFoundError(
        f"\nPut a test image here first:\n"
        f"{os.path.abspath(image_path)}"
    )

os.makedirs(output_path, exist_ok=True)

print("Running OCR...")

model.infer(
    tokenizer,
    prompt="<image>document parsing.",
    image_file=image_path,
    output_path=output_path,
    base_size=1024,
    image_size=640,
    crop_mode=True,
    max_length=32768,
    no_repeat_ngram_size=35,
    ngram_window=128,
    save_results=True,
)

print("\nOCR finished.")
print("Output directory:", os.path.abspath(output_path))
