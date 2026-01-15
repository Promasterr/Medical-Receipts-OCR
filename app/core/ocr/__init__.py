"""OCR module exports"""
from app.core.ocr.inference import run_batch_inference, image_to_base64
from app.core.ocr.prompts import get_prompt_by_keyword

__all__ = [
    "run_batch_inference",
    "image_to_base64",
    "get_prompt_by_keyword",
]
