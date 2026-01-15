"""
Image preprocessing including barcode removal.
"""
import numpy as np
import cv2
from PIL import Image
from typing import Union
from app.models.ml_models import model_manager


def remove_barcode(
    img: Union[np.ndarray, Image.Image],
    expand_w: float = 0.1,
    expand_h: float = 0.4
) -> Image.Image:
    """
    Detect barcode → expand bounding box → whiten pixels.
    Accepts image array or PIL Image directly.
    
    Args:
        img: Input image as numpy array or PIL Image
        expand_w: Horizontal expansion factor for bbox
        expand_h: Vertical expansion factor for bbox
        
    Returns:
        PIL Image with barcode region whitened
    """
    barcode_model = model_manager.barcode_model
    
    # Convert PIL Image to numpy array if needed
    if isinstance(img, Image.Image):
        img_array = np.array(img)
    else:
        img_array = img.copy()
    
    # Detect barcodes
    results = barcode_model(img_array)
    
    # Process each detection
    for result in results:
        boxes = result.boxes
        
        if boxes is None or len(boxes) == 0:
            continue
        
        for box in boxes:
            # Get bounding box coordinates
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            # Calculate expansion
            w = x2 - x1
            h = y2 - y1
            expand_w_px = int(w * expand_w)
            expand_h_px = int(h * expand_h)
            
            # Expand bounding box
            x1_expanded = max(0, x1 - expand_w_px)
            y1_expanded = max(0, y1 - expand_h_px)
            x2_expanded = min(img_array.shape[1], x2 + expand_w_px)
            y2_expanded = min(img_array.shape[0], y2 + expand_h_px)
            
            # Whiten the barcode region
            img_array[y1_expanded:y2_expanded, x1_expanded:x2_expanded] = 255
    
    # Convert back to PIL Image
    return Image.fromarray(img_array)
