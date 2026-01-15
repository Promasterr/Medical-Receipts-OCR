"""
Layout detection using PP-DocLayoutV2 model.
"""
from typing import List, Dict, Any
from app.models.ml_models import model_manager


def process_layout(img_path: str) -> List[Dict[str, Any]]:
    """
    Loads the layout detection model, runs prediction on the specified image path,
    and extracts all detected labels and bounding boxes.

    Args:
        img_path (str): The file path to the image/document to process.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing the page number,
                              label, and bounding box for each detected element.
    """
    layout_model = model_manager.layout_model
    
    # Run layout detection
    try:
        layout_results = layout_model.predict(
            img_path,
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
                extracted_data.append({
                    "page_id": page_id,
                    "label": label,
                    "score": score,
                    "bbox": bbox
                })
    return extracted_data
