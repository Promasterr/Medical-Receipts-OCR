"""
Janzour template processor (also handles Safwa template - they are similar).
Extracts Janzour-specific processing logic with ID card detection.
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
    crop_below_bbox,
    crop_from_upper,
    remove_barcode,
    predict_qr_detection,
    process_and_crop_qr_region,
    run_batch_inference,
    default_progress_callback,
    get_prompt_by_keyword,
    _run_single_inference_task
)


async def prepare_janzour_page(image_path: str) -> Optional[Dict]:
    """
    Prepare input for a single page using Janzour template logic.
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
    except Exception as e:
        print(f"prepare_janzour_page: layout error for {image_path}: {e}")
        return None

    # Flags and items
    doc_title = next((item for item in results if item["label"] == "doc_title"), None)
    footer = next((item for item in results if item["label"] == "footer"), None)
    paragraph_title = next((item for item in results if item["label"] == "paragraph_title"), None)
    has_table = any(item["label"] == "table" for item in results)
    has_header = any(item["label"] in ("header", "header_image") for item in results)
    

    final_image = None
    keyword = "janzour"
    mode = "janzour"

    if doc_title is None:
        if paragraph_title is not None:
            crop = crop_region_from_image(image_path, paragraph_title["bbox"])
        
            # Perform OCR on the cropped doc_title
            ocr_job = {
                "image": crop,
                "prompt": "extract the arabic text"
            }
            
            try:
                # Run OCR to check the title
                ocr_result = await _run_single_inference_task(ocr_job, max_new_tokens=512)
                print(f"prepare_janzour_page: ocr_result: {ocr_result}")
                if "إيصال" in ocr_result and "رقم" in ocr_result:
                    keyword="janzour"
                    mode="janzour"
                    img = cv2.imread(image_path)
                    final_image = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                else:
                    print(f"prepare_janzour_page: skip (paragraph_title OCR check failed) — {image_path}")
                    return None
            except Exception as e:
                print(f"prepare_janzour_page: OCR error on doc_title: {e}")
                return None
        else:
            # Fall through to check for ID card
            pass

    if (not has_table) and has_header:
        qr_detections = predict_qr_detection(input_image_cv)
        if len(qr_detections) > 0:
            print(f"prepare_janzour_page: idcard detected for {image_path}")
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
            if cropped_cv is not None:
                final_image = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
                keyword = "idcard"
                mode = "idcard"
            else:
                return None
        else:
            print(f"prepare_janzour_page: skip (no qr and not header+table) — {image_path}")
            return None

    # ID Card: fallback path when no header+table
    elif not (has_header and has_table):
        qr_detections = predict_qr_detection(input_image_cv)
        if len(qr_detections) > 0:
            print(f"prepare_janzour_page: idcard detected for {image_path}")
            image_bboxes = [
                {
                    "label": item["label"],
                    "bbox": item["bbox"],
                }
                for item in results if item["label"] == "image"
            ]
            cropped_cv = process_and_crop_qr_region(
                input_image_cv, qr_detections, image_bboxes,
                expansion_factor_up=4.0, expansion_factor_right=5.9,
            )
            if cropped_cv is not None:
                final_image = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
                keyword = "idcard"
                mode = "idcard"
            else:
                return None
        else:
            print(f"prepare_janzour_page: skip (no qr and not header+table) — {image_path}")
            return None
    # Janzour: doc_title + table
    elif doc_title is not None:
        print(f"prepare_janzour_page: janzour detected for {image_path}")
        
    
        
        
        cropped = crop_below_bbox(image_path, doc_title["bbox"])
        cropped = remove_barcode(cropped)
        final_image = cropped
        if footer is not None:
            final_image = crop_from_upper(final_image, footer["bbox"])

    prompt = get_prompt_by_keyword(keyword)

    # Safety check: ensure we have a valid image before returning
    if final_image is None:
        print(f"prepare_janzour_page: skip (no valid image generated) — {image_path}")
        return None

    return {
        "image": final_image,
        "prompt": prompt,
        "mode": mode,
        "original_path": image_path,
    }


async def process_janzour_pdf(pdf_path: str, temp_dir: str, progress_callback=None):
    """
    Complete processing pipeline for Janzour template PDFs.
    
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

    # STEP 2 — Preprocessing (Janzour-specific)
    batch_jobs = []
    skipped_pages = []

    for idx, image_path in enumerate(extracted_images):
        try:
            job = await prepare_janzour_page(image_path)
            if job:
                job["page_index"] = idx
                batch_jobs.append(job)
            else:
                skipped_pages.append({"page_index": idx, "status": "skipped"})
        except Exception as e:
            skipped_pages.append({"page_index": idx, "error": str(e)})

    await progress_callback("progress", {
        "step": "preprocessing",
        "prepared_pages": len(batch_jobs),
        "skipped_pages": len(skipped_pages)
    })

    # STEP 3 — OCR
    await progress_callback("progress", {
        "step": "ocr",
        "message": "Running batch OCR inference"
    })

    raw_results = []
    if batch_jobs:
        raw_results = await run_batch_inference(batch_jobs, max_new_tokens=11000)

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
        elif mode == "janzour":
            separator = "===========page==========="
        else:
            separator = "===========page==========="  # default
        
        # Add separator before the result
        results_with_separators.append(f"{separator}\n{result}")
    
    joined = "\n".join(results_with_separators)
    
    return joined, skipped_pages
