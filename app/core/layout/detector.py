"""
Layout detection using PP-DocLayoutV2 model.
"""
from typing import List, Dict, Any
from app.models.ml_models import model_manager


import cv2
import numpy as np

def process_layout(img_path: str) -> List[Dict[str, Any]]:
    """
    Loads the layout detection model, runs prediction on the specified image path,
    and extracts all detected labels and bounding boxes.
    
    Implements 'Two-Track Resolution': 
    - Downscales image to max 1000px for layout detection (VRAM saving)
    - Scales bounding boxes back to original resolution for downstream OCR
    """
    # Lazy load the model only when this function is actually called
    layout_model = model_manager.initialize_layout_model()
    
    # Run layout detection
    try:
        # Load image for optional resizing
        img = cv2.imread(img_path)
        if img is None:
            raise ValueError(f"Could not read image: {img_path}")
            
        # Optimization: Resize if too large to save VRAM
        h, w = img.shape[:2]
        target_max = 1000.0
        scale = 1.0
        model_input = img_path  # Default to path
        
        if max(h, w) > target_max:
            scale = target_max / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            # Use INTER_AREA for downscaling to avoid artifacts
            resized_img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            model_input = resized_img
            
        layout_results = layout_model.predict(
            model_input,
            batch_size=1,
            layout_nms=True,
            threshold=0.42
        )
    except Exception as e:
        print(f"ERROR: Layout detection failed: {e}")
        return []
    
    extracted_data = []
    
    if not layout_results:
        return extracted_data
    
    for page_index, page in enumerate(layout_results):
        page_id = page.get("page_id", page_index)
        boxes = page.get("boxes", [])
        
        for box in boxes:
            label = box.get("label")
            bbox = box.get("coordinate")  # Actual key from model output
            score = box.get("score")
            
            if label and bbox:
                # Rescale bbox back to original resolution if needed
                if scale != 1.0:
                    # [x1, y1, x2, y2]
                    bbox = [int(round(coord * (1/scale))) for coord in bbox]
                
                extracted_data.append({
                    "page_id": page_id,
                    "label": label,
                    "score": score,
                    "bbox": bbox
                })
    return extracted_data
