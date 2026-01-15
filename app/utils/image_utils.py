"""
Image manipulation utilities (cropping, etc.)
All operations are in-memory - no file saving.
"""
from PIL import Image
from typing import Union


def crop_region_from_image(image_path: Union[str, Image.Image], bbox: list) -> Image.Image:
    """
    Crop a region from an image using bbox = [x1, y1, x2, y2]
    
    Args:
        image_path: File path to image or PIL Image object
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        
    Returns:
        Cropped PIL Image
    """
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    
    x1, y1, x2, y2 = bbox
    cropped = img.crop((x1, y1, x2, y2))
    
    return cropped


def crop_below_bbox(image_path: Union[str, Image.Image], bbox: list) -> Image.Image:
    """
    Crop the image to remove everything above the bbox.
    bbox = [x1, y1, x2, y2]
    
    Args:
        image_path: File path to image or PIL Image object
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        
    Returns:
        Cropped PIL Image (area from bbox.y1 to bottom)
    """
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    
    # Ensure numeric bbox
    x1, y1, x2, y2 = map(float, bbox)
    
    # Crop area: start from y1 to bottom of image
    crop_box = (0, int(y1), img.width, img.height)
    cropped = img.crop(crop_box)
    
    return cropped


def crop_from_lower(image_path: Union[str, Image.Image], bbox: list, offset: int = 50) -> Image.Image:
    """
    Crop the image starting from the bottom of the bbox to the bottom of the image.
    bbox = [x1, y1, x2, y2]
    Keeps the area BELOW the bbox (from y2 to bottom of image).
    
    Args:
        image_path: File path to image or PIL Image object
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        offset: Pixels to offset from bbox bottom
        
    Returns:
        Cropped PIL Image
    """
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    
    # Ensure numeric bbox
    x1, y1, x2, y2 = map(float, bbox)
    
    start_y = int(y2) + offset
    # Crop area: start from y2 to bottom
    crop_box = (0, int(start_y), img.width, img.height)
    cropped = img.crop(crop_box)
    
    return cropped


def crop_from_upper(image_path: Union[str, Image.Image], bbox: list, offset: int = 50) -> Image.Image:
    """
    Crop the image starting from the top of the image to the top of the bbox.
    bbox = [x1, y1, x2, y2]
    Keeps the area ABOVE the bbox (from top to y1 - offset).
    
    Args:
        image_path: File path to image or PIL Image object
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        offset: Pixels to offset from bbox top
        
    Returns:
        Cropped PIL Image
    """
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    
    # Ensure numeric bbox
    x1, y1, x2, y2 = map(float, bbox)
    
    end_y = int(y1) - offset
    end_y = max(0, end_y)  # Prevent negative crop
    
    # Crop area: from top to y1-offset
    crop_box = (0, 0, img.width, end_y)
    cropped = img.crop(crop_box)
    
    return cropped


def vertical_distance(b1: list, b2: list) -> float:
    """
    Distance between:
        - lower Y of first bbox  (b1[3])
        - upper Y of second bbox (b2[1])
    
    Args:
        b1: First bounding box [x1, y1, x2, y2]
        b2: Second bounding box [x1, y1, x2, y2]
        
    Returns:
        Vertical distance in pixels
    """
    try:
        y1_lower = float(b1[3])
        y2_upper = float(b2[1])
        return y2_upper - y1_lower
    except (IndexError, TypeError, ValueError):
        return 0.0
