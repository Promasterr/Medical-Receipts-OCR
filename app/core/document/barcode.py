"""
QR code and barcode detection with orientation correction.
"""
import cv2
import numpy as np
from typing import List, Dict, Optional
from app.models.ml_models import model_manager


def get_finder_patterns(cropped_qr_image: np.ndarray) -> List[tuple]:
    """
    Uses OpenCV to detect the three finder patterns (squares) in a cropped QR code image.
    Returns: A list of (x, y) center coordinates.
    """
    if cropped_qr_image.size == 0:
        return []
    
    gray = cv2.cvtColor(cropped_qr_image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    pattern_centers = []
    
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        
        area = cv2.contourArea(contour)
        if len(approx) == 4 and area > 100:
            x, y, w, h = cv2.boundingRect(contour)
            if 0.8 < w/h < 1.2:
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    pattern_centers.append((cX, cY))
    
    return pattern_centers


def determine_orientation(pattern_centers: List[tuple]) -> int:
    """
    Analyzes the relative positions of the three finder patterns to determine 0 or 180 degrees rotation.
    """
    if len(pattern_centers) < 3:
        return 0
    
    y_coords = sorted([p[1] for p in pattern_centers])
    
    dist_0_1 = abs(y_coords[1] - y_coords[0])
    dist_1_2 = abs(y_coords[2] - y_coords[1])
    
    if dist_0_1 < dist_1_2:
        return 0  # Pair is at the top
    else:
        return 180  # Pair is at the bottom


def predict_qr_detection(image: np.ndarray) -> List[Dict]:
    """
    Runs the QRDetector on the image and returns all detected QR codes.
    
    Args:
        image (np.ndarray): The input image (BGR format).
        
    Returns:
        list: A list of dictionaries, where each dictionary represents a detection.
    """
    detector = model_manager.qr_detector
    detections = detector.detect(image=image, is_bgr=True)
    return detections


def process_and_crop_qr_region(
    image: np.ndarray,
    detections: List[Dict],
    image_bboxes: List[Dict],
    expansion_factor_up: float = 4,
    expansion_factor_right: float = 5.8
) -> Optional[np.ndarray]:
    """
    Process QR detection, determine orientation, rotate image, whiten layout bboxes, and crop ID card region.
    
    Args:
        image: Input image array
        detections: QR detection results
        image_bboxes: Layout detection bounding boxes to whiten
        expansion_factor_up: Vertical expansion factor
        expansion_factor_right: Horizontal expansion factor
        
    Returns:
        Cropped and processed image array or None
    """
    if not detections:
        return None
    
    h_orig, w_orig, _ = image.shape
    orientation_angle = 0
    
    target_detection = detections[0]
    x1, y1, x2, y2 = map(int, target_detection['bbox_xyxy'])
    
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_orig, x2), min(h_orig, y2)
    
    cropped_image_qr = image[y1:y2, x1:x2]
    
    if cropped_image_qr.size > 0:
        pattern_centers_local = get_finder_patterns(cropped_image_qr)
        if len(pattern_centers_local) >= 3:
            orientation_angle = determine_orientation(pattern_centers_local)
    
    # Apply rotation
    rotated_image = image.copy()
    
    if orientation_angle == 180:
        rotated_image = cv2.rotate(rotated_image, cv2.ROTATE_180)
        h_rot, w_rot, _ = rotated_image.shape
    else:
        h_rot, w_rot = h_orig, w_orig
    
    # Whiten all image bboxes
    for item in image_bboxes:
        bx1, by1, bx2, by2 = map(int, item["bbox"])
        
        # Transform bbox if rotated
        if orientation_angle == 180:
            bx1r = w_orig - bx2
            by1r = h_orig - by2
            bx2r = w_orig - bx1
            by2r = h_orig - by1
            
            bx1r, bx2r = min(bx1r, bx2r), max(bx1r, bx2r)
            by1r, by2r = min(by1r, by2r), max(by1r, by2r)
        else:
            bx1r, by1r, bx2r, by2r = bx1, by1, bx2, by2
        
        # Clamp to image bounds
        bx1r = max(0, bx1r)
        by1r = max(0, by1r)
        bx2r = min(w_rot, bx2r)
        by2r = min(h_rot, by2r)
        
        # Paint white
        rotated_image[by1r:by2r, bx1r:bx2r] = 255
    
    # Transform QR bbox
    x1o, y1o, x2o, y2o = map(int, target_detection['bbox_xyxy'])
    
    if orientation_angle == 180:
        x1r = w_orig - x2o
        y1r = h_orig - y2o
        x2r = w_orig - x1o
        y2r = h_orig - y1o
        
        x1r, x2r = min(x1r, x2r), max(x1r, x2r)
        y1r, y2r = min(y1r, y2r), max(y1r, y2r)
    else:
        x1r, y1r, x2r, y2r = x1o, y1o, x2o, y2o
    
    # Expand & crop
    w_box = x2r - x1r
    h_box = y2r - y1r
    
    y1_final = int(y2r - h_box * expansion_factor_up)
    x2_final = int(x1r + w_box * expansion_factor_right)
    
    x1_final = max(0, x1r)
    y1_final = max(0, y1_final)
    x2_final = min(w_rot, x2_final)
    y2_final = min(h_rot, y2r)
    
    cropped_final = rotated_image[y1_final:y2_final, x1_final:x2_final]
    
    if cropped_final.size == 0:
        return None
    
    return cropped_final
