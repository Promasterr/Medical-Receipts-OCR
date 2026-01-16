"""
Massara template processor (also handles Muasafat template - they are similar).
Extracts Massara-specific processing logic with ID card detection.
"""
import os
import cv2
import numpy as np
from typing import Dict, List, Optional, Any
from PIL import Image

from app.core.document.pdf_processor import (
    extract_images_from_pdf,
    process_layout,
    crop_region_from_image,
    crop_from_lower,
    crop_from_upper,
    remove_barcode,
    predict_qr_detection,
    process_and_crop_qr_region,
    run_batch_inference,
    default_progress_callback,
    get_prompt_by_keyword,
    _run_single_inference_task
)


async def prepare_massara_page(image_path: str) -> Optional[Dict]:
    """
    Prepare input for a single page using Massara template logic.
    Includes ID card detection as fallback.
    
    Returns:
        Dict with image, prompt, mode, and original_path or None if page should be skipped
    """
    # Load raw (cv2) for layout/qr detectors
    input_image_cv = cv2.imread(image_path)
    if input_image_cv is None:
        print(f"Error loading image: {image_path}")
        return None

    try:
        results = process_layout(image_path)
        print(results)
    except Exception as e:
        print(f"prepare_massara_page: layout error for {image_path}: {e}")
        return None

    # Flags and items
    doc_title = next((item for item in results if item["label"] == "doc_title"), None)
    footer = next((item for item in results if item["label"] == "footer"), None)
    paragraph_title = next((item for item in results if item["label"] == "paragraph_title"), None)
    header_image = next((item for item in results if item["label"] == "header_image"), None)
    header = next((item for item in results if item["label"] == "header"), None)
    has_table = any(item["label"] == "table" for item in results)
    has_header = any(item["label"] in ("header", "header_image") for item in results)

    final_image = None
    keyword = "massara"
    mode = "massara"


    # Massara: no doc_title and no paragraph_title
    if doc_title is None and paragraph_title is None and has_table:
        print(f"prepare_massara_page: massara detected for {image_path}")
        target_header = header_image if header_image else header
        if target_header:
            final_image = crop_from_lower(image_path, target_header["bbox"])
        else:
            final_image = Image.open(image_path).convert("RGB")
            
        final_image = remove_barcode(final_image)
        if footer is not None:
            final_image = crop_from_upper(final_image, footer["bbox"])

    # Massara medicine case: doc_title None and paragraph_title present
    elif doc_title is not None or paragraph_title is not None and has_table:
        print(f"prepare_massara_page: massara medicine for {image_path}")
        
        # Crop the paragraph title and check if it should be skipped
        if paragraph_title is not None:
            crop = crop_region_from_image(image_path, paragraph_title["bbox"])
        else:
            crop = crop_region_from_image(image_path, doc_title["bbox"])
        
        # Perform OCR on the cropped paragraph title
        ocr_job = {
            "image": crop,
            "prompt": "extract the arabic text"
        }
        
        try:
            # Run OCR to check the title
            ocr_result = await _run_single_inference_task(ocr_job, max_new_tokens=512)
            print(f"prepare_massara_page: ocr_result: {ocr_result}")
            # Check if result contains the skip phrase
            if isinstance(ocr_result, str) and "أدوية ومستلزمات من الايواء" in ocr_result:
                print(f"prepare_massara_page: skipping page - contains 'أدوية ومستلزمات من الايواء'")
                return None
            elif isinstance(ocr_result, str) and ("ورقة خروج" in ocr_result or "Discharge Paper" in ocr_result):
                print(f"prepare_massara_page: skipping page - contains 'Discharge Paper'")
                return None
        
        except Exception as e:
            print(f"prepare_massara_page: OCR error on paragraph_title: {e}")
            # Continue processing even if OCR fails
        
        keyword = "massara medicine"
        final_image = Image.open(image_path).convert("RGB")
        final_image = remove_barcode(final_image)
        mode = "massara"
    
   

    # ID Card: fallback path when no header+table
    elif not has_table:
        qr_detections = predict_qr_detection(input_image_cv)
        if len(qr_detections) > 0:
            print(f"prepare_massara_page: idcard detected for {image_path}")
            image_bboxes = [
                {
                    "label": item["label"],
                    "bbox": item["bbox"],
                }
                for item in results if item["label"] == "image"
            ]
            cropped_cv = process_and_crop_qr_region(
                input_image_cv, qr_detections, image_bboxes,
                expansion_factor_up=4.0, expansion_factor_right=5.8,
            )
            cv2.imwrite("cv_image.jpg", cropped_cv)
            if cropped_cv is not None:
                final_image = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
                keyword = "idcard"
                mode = "idcard"
            else:
                return None
        else:
            print(f"prepare_massara_page: skip (no qr and not header+table) — {image_path}")
            return None
    elif not has_table:
        print(f"prepare_massara_page: skipping page - no table found")
        return None
    # Default fallback (shouldn't normally reach here)
    else:
        final_image = Image.open(image_path).convert("RGB")
        keyword = "massara"
        mode = "massara"

    prompt = get_prompt_by_keyword(keyword)

    # Safety check: ensure we have a valid image before returning
    if final_image is None:
        print(f"prepare_massara_page: skip (no valid image generated) — {image_path}")
        return None

    return {
        "image": final_image,
        "prompt": prompt,
        "mode": mode,
        "original_path": image_path,
    }


import uuid

async def preprocess_pdf_async(pdf_path: str, temp_dir: str):
    """
    Async generator that yields preprocessed Massara images one at a time.
    
    This streams preprocessing results to enable the buffered pipeline pattern
    instead of preprocessing all pages before starting inference.
    
    Args:
        pdf_path: Path to PDF file
        temp_dir: Temporary directory for intermediate files
    
    Yields:
        Dict containing:
            - uuid: Unique identifier for this page
            - image: Preprocessed PIL Image
            - prompt: OCR prompt string
            - metadata: Dict with pdf_path, page_num, mode, pdf_name
    """
    from pathlib import Path
    pdf_name = Path(pdf_path).stem
    pdf_images_dir = os.path.join(temp_dir, f"{pdf_name}_images")
    os.makedirs(pdf_images_dir, exist_ok=True)

    # Extract all images first (this is fast, CPU-bound)
    extracted_images = extract_images_from_pdf(pdf_path, pdf_images_dir)
    
    # Yield preprocessed images one at a time
    for idx, image_path in enumerate(extracted_images):
        try:
            job = await prepare_massara_page(image_path)
            if job:
                # Add UUID and metadata
                job["uuid"] = str(uuid.uuid4())
                job["metadata"] = {
                    "pdf_path": pdf_path,
                    "pdf_name": pdf_name,
                    "page_num": idx,
                    "mode": job.get("mode", "massara")
                }
                yield job
            else:
                # Yield a skip marker
                yield {
                    "uuid": str(uuid.uuid4()),
                    "metadata": {
                        "pdf_path": pdf_path,
                        "pdf_name": pdf_name,
                        "page_num": idx,
                        "status": "skipped"
                    },
                    "skipped": True
                }
        except Exception as e:
            # Yield error marker
            yield {
                "uuid": str(uuid.uuid4()),
                "metadata": {
                    "pdf_path": pdf_path,
                    "pdf_name": pdf_name,
                    "page_num": idx,
                    "error": str(e),
                    "status": "error"
                },
                "skipped": True
            }



async def process_massara_pdf(pdf_path: str, temp_dir: str, progress_callback=None):
    """
    Complete processing pipeline for Massara template PDFs.
    
    Args:
        pdf_path: Path to PDF file
        temp_dir: Temporary directory for intermediate files
        progress_callback: Optional async callback for progress updates
        
    Returns:
        Tuple of (joined_text, skipped_pages)
    """
    if progress_callback is None:
        progress_callback = default_progress_callback
    
    from pathlib import Path
    pdf_name = Path(pdf_path).stem
    pdf_images_dir = os.path.join(temp_dir, f"{pdf_name}_images")
    os.makedirs(pdf_images_dir, exist_ok=True)

    # STEP 1 — Extract images
    await progress_callback("progress", {
        "step": "extract_images",
        "message": "Extracting images from PDF"
    })

    extracted_images = extract_images_from_pdf(pdf_path, pdf_images_dir)

    await progress_callback("progress", {
        "step": "extract_images",
        "pages": len(extracted_images),
        "status": "done"
    })

    # STEP 2 — Preprocessing (Massara-specific)
    batch_jobs = []
    skipped_pages = []
    
    print(f"DEBUG: Starting preprocessing for {len(extracted_images)} extracted images")

    for idx, image_path in enumerate(extracted_images):
        try:
            print(f"DEBUG: Processing page {idx + 1}/{len(extracted_images)}: {image_path}")
            job = await prepare_massara_page(image_path)
            if job:
                print(f"DEBUG: Page {idx + 1} prepared successfully. Mode: {job.get('mode')}")
                job["page_index"] = idx
                batch_jobs.append(job)
            else:
                print(f"DEBUG: Page {idx + 1} skipped (prepare_massara_page returned None)")
                skipped_pages.append({"page_index": idx, "status": "skipped"})
        except Exception as e:
            print(f"ERROR: Failed to process page {idx + 1}: {e}")
            skipped_pages.append({"page_index": idx, "error": str(e)})

    print(f"DEBUG: Preprocessing complete. Total jobs: {len(batch_jobs)}, Skipped: {len(skipped_pages)}")

    await progress_callback("progress", {
        "step": "preprocessing",
        "prepared_pages": len(batch_jobs),
        "skipped_pages": len(skipped_pages)
    })

    # STEP 3 — OCR
    print(f"DEBUG: Starting batch inference with {len(batch_jobs)} jobs")
    await progress_callback("progress", {
        "step": "ocr",
        "message": "Running batch OCR inference"
    })

    raw_results = []
    if batch_jobs:
        raw_results = await run_batch_inference(batch_jobs, max_new_tokens=11000)
    print(raw_results)
    await progress_callback("progress", {
        "step": "ocr",
        "status": "done"
    })

    # Add separators before each page based on mode
    results_with_separators = []
    for job, result in zip(batch_jobs, raw_results):
        mode = job.get("mode", "")
        
        # Determine separator based on mode
        if mode == "idcard":
            separator = "============ ID Card ==========="
        elif mode == "massara":
            separator = "===========page==========="
        else:
            separator = "===========page==========="  # default
        
        # Add separator before the result
        results_with_separators.append(f"{separator}\n{result}")
    
    joined = "\n".join(results_with_separators)
    print(f"DEBUG: Joined raw text length: {len(joined)}")
    print(f"DEBUG: Raw text snippet (first 500 chars):\n{joined[:500]}")
    
    return joined, skipped_pages
